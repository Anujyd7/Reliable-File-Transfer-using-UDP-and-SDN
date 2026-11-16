import socket
import os
import sys
import time
import math
import uuid
import argparse

from protocol.reliability import (
    SERVER_IP,
    SERVER_PORT,
    CHUNK_SIZE,
    WINDOW_SIZE,
    ACK_TIMEOUT,
    MAX_RETRIES,
    MAX_DATAGRAM_SIZE,
    START,
    DATA,
    ACK,
    FIN,
    DONE,
    ERROR,
    START_ACK_SEQ,
    create_packet,
    decode_packet,
    calculate_sha256,
    encode_metadata
)

# ==========================================
# CLIENT CONFIGURATION
# ==========================================

def send_file(filename, server_ip, server_port):

    if not os.path.isfile(filename):

        print("[CLIENT] ERROR: File does not exist")
        return False

    with open(filename, "rb") as file:

        file_data = file.read()

    filename_only = os.path.basename(filename)

    total_packets = math.ceil(
        len(file_data) / CHUNK_SIZE
    )

    file_hash = calculate_sha256(file_data)

    # Divide file into chunks
    chunks = [
        file_data[i:i + CHUNK_SIZE]
        for i in range(0, len(file_data), CHUNK_SIZE)
    ]

    # Unique transfer identifier
    transfer_id = uuid.uuid4().bytes

    metadata = {
        "filename": filename_only,
        "file_size": len(file_data),
        "total_packets": total_packets,
        "chunk_size": CHUNK_SIZE,
        "sha256": file_hash
    }

    server_address = (
        server_ip,
        server_port
    )

    client = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    client.settimeout(0.05)

    print("\n" + "=" * 60)
    print("          RELIABLE UDP FILE TRANSFER CLIENT")
    print("=" * 60)

    print(f"[CLIENT] File: {filename_only}")
    print(f"[CLIENT] Size: {len(file_data)} bytes")
    print(f"[CLIENT] Total packets: {total_packets}")
    print(f"[CLIENT] Server: {server_ip}:{server_port}")
    print(f"[CLIENT] SHA256: {file_hash}")

    # ======================================
    # START HANDSHAKE
    # ======================================

    start_packet = create_packet(
        START,
        transfer_id,
        0,
        total_packets,
        encode_metadata(metadata)
    )

    print("\n[CLIENT] Starting transfer...")

    initialized = False

    for attempt in range(MAX_RETRIES):

        client.sendto(
            start_packet,
            server_address
        )

        try:

            response, address = client.recvfrom(
                MAX_DATAGRAM_SIZE
            )

            if address != server_address:
                continue

            (
                packet_type,
                received_id,
                sequence,
                received_total,
                payload
            ) = decode_packet(response)

            if received_id != transfer_id:
                continue

            if packet_type == ERROR:

                raise RuntimeError(
                    payload.decode(errors="replace")
                )

            if (
                packet_type == ACK
                and sequence == START_ACK_SEQ
                and received_total == total_packets
            ):

                initialized = True
                break

        except socket.timeout:

            print(
                f"[CLIENT] Waiting for initialization ACK "
                f"({attempt + 1}/{MAX_RETRIES})"
            )

    if not initialized:

        print("[CLIENT] ERROR: Server initialization failed")
        client.close()
        return False

    print("[CLIENT] Server ready")

    # ======================================
    # SELECTIVE REPEAT ARQ
    # ======================================

    acknowledged = set()

    retries = {}
    last_sent = {}

    base = 0
    next_packet = 0

    retransmissions = 0

    transfer_start = time.monotonic()

    print("\n[CLIENT] Sending packets...")

    while base < total_packets:

        # ----------------------------------
        # SEND NEW PACKETS IN THE WINDOW
        # ----------------------------------

        while (
            next_packet < total_packets
            and next_packet < base + WINDOW_SIZE
        ):

            packet = create_packet(
                DATA,
                transfer_id,
                next_packet,
                total_packets,
                chunks[next_packet]
            )

            client.sendto(
                packet,
                server_address
            )

            last_sent[next_packet] = time.monotonic()
            retries[next_packet] = 0

            print(
                f"[CLIENT] Sent packet "
                f"{next_packet + 1}/{total_packets}"
            )

            next_packet += 1

        # ----------------------------------
        # RECEIVE ACKNOWLEDGMENTS
        # ----------------------------------

        try:

            response, address = client.recvfrom(
                MAX_DATAGRAM_SIZE
            )

            if address != server_address:
                continue

            (
                packet_type,
                received_id,
                sequence,
                received_total,
                payload
            ) = decode_packet(response)

            if received_id != transfer_id:
                continue

            if packet_type == ERROR:

                raise RuntimeError(
                    payload.decode(errors="replace")
                )

            if packet_type == ACK:

                if received_total != total_packets:
                    continue

                if 0 <= sequence < total_packets:

                    if sequence not in acknowledged:

                        acknowledged.add(sequence)

                        print(
                            f"[CLIENT] ACK received: "
                            f"{sequence + 1}/{total_packets}"
                        )

        except socket.timeout:

            pass

        # ----------------------------------
        # CHECK FOR TIMEOUTS
        # ----------------------------------

        current_time = time.monotonic()

        for sequence in range(base, next_packet):

            if sequence in acknowledged:
                continue

            if sequence not in last_sent:
                continue

            elapsed = (
                current_time - last_sent[sequence]
            )

            if elapsed >= ACK_TIMEOUT:

                if retries[sequence] >= MAX_RETRIES:

                    print(
                        f"[CLIENT] ERROR: Maximum retries "
                        f"reached for packet {sequence + 1}"
                    )

                    client.close()
                    return False

                retry_packet = create_packet(
                    DATA,
                    transfer_id,
                    sequence,
                    total_packets,
                    chunks[sequence]
                )

                client.sendto(
                    retry_packet,
                    server_address
                )

                retries[sequence] += 1
                retransmissions += 1

                last_sent[sequence] = time.monotonic()

                print(
                    f"[CLIENT] Retransmitting packet "
                    f"{sequence + 1}, "
                    f"attempt {retries[sequence]}"
                )

        # ----------------------------------
        # MOVE SLIDING WINDOW
        # ----------------------------------

        while base in acknowledged:

            base += 1

    transfer_time = (
        time.monotonic() - transfer_start
    )

# ======================================
    # FINISH HANDSHAKE
    # ======================================

    fin_packet = create_packet(
        FIN,
        transfer_id,
        0,
        total_packets
    )

    print("\n[CLIENT] All packets acknowledged")
    print("[CLIENT] Sending FIN...")

    completed = False

    for attempt in range(MAX_RETRIES):

        client.sendto(
            fin_packet,
            server_address
        )

        # Wait for DONE while ignoring delayed or duplicate ACKs.
        deadline = time.monotonic() + ACK_TIMEOUT

        while True:
            remaining = deadline - time.monotonic()

            if remaining <= 0:
                break

            client.settimeout(remaining)

            try:
                response, address = client.recvfrom(
                    MAX_DATAGRAM_SIZE
                )

            except socket.timeout:
                break

            if address != server_address:
                continue

            try:
                (
                    packet_type,
                    received_id,
                    sequence,
                    received_total,
                    payload
                ) = decode_packet(response)

            except ValueError:
                continue

            if received_id != transfer_id:
                continue

            if packet_type == ERROR:
                raise RuntimeError(
                    payload.decode(errors="replace")
                )

            if (
                packet_type == DONE
                and received_total == total_packets
            ):
                completed = True
                break

            # Ignore delayed ACKs and unrelated packets.
            continue

        if completed:
            break

        print(
            f"[CLIENT] Waiting for server completion "
            f"({attempt + 1}/{MAX_RETRIES})"
        )

    client.close()

    if not completed:
        print("[CLIENT] ERROR: Completion confirmation missing")
        return False
    # ======================================
    # PERFORMANCE SUMMARY
    # ======================================

    throughput = 0

    if transfer_time > 0:

        throughput = (
            len(file_data) * 8
            / transfer_time
            / 1_000_000
        )

    print("\n" + "=" * 60)
    print("          FILE TRANSFER COMPLETED")
    print("=" * 60)

    print(f"File: {filename_only}")
    print(f"Packets acknowledged: {len(acknowledged)}")
    print(f"Retransmissions: {retransmissions}")
    print(f"Transfer time: {transfer_time:.3f} seconds")
    print(f"Throughput: {throughput:.3f} Mbps")

    print("Server integrity confirmation: PASSED")

    return True

# ==========================================
# MAIN
# ==========================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Reliable UDP File Transfer Client"
    )

    parser.add_argument(
        "file",
        help="Path of the file to transfer"
    )

    parser.add_argument(
        "--host",
        default=SERVER_IP,
        help="Server IP address"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=SERVER_PORT,
        help="Server UDP port"
    )

    args = parser.parse_args()

    try:

        send_file(
            args.file,
            args.host,
            args.port
        )

    except KeyboardInterrupt:

        print("\n[CLIENT] Transfer interrupted")

    except Exception as error:

        print(f"\n[CLIENT] ERROR: {error}")
