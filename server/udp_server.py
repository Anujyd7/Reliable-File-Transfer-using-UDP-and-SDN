import socket
import os
import re
import time

from protocol.reliability import (
    SERVER_PORT,
    HEADER,
    START,
    DATA,
    ACK,
    FIN,
    DONE,
    ERROR,
    START_ACK_SEQ,
    MAX_DATAGRAM_SIZE,
    decode_packet,
    decode_metadata,
    create_packet,
    calculate_sha256
)

# ==========================================
# SERVER CONFIGURATION
# ==========================================

HOST = "0.0.0.0"
PORT = SERVER_PORT

OUTPUT_DIR = "received_files"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ==========================================
# UDP SERVER
# ==========================================

def start_server():

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server.bind((HOST, PORT))

    print("=" * 60)
    print("          RELIABLE UDP FILE TRANSFER SERVER")
    print("=" * 60)

    print(f"[SERVER] Listening on {HOST}:{PORT}")
    print("[SERVER] Waiting for clients...\n")

    # Current transfer state
    transfer_id = None
    client_address = None
    metadata = None

    received_packets = {}
    total_packets = 0
    completed = False

    while True:

        packet, address = server.recvfrom(
            MAX_DATAGRAM_SIZE
        )

        try:

            (
                packet_type,
                packet_transfer_id,
                sequence,
                total,
                payload
            ) = decode_packet(packet)

        except ValueError:

            print("[SERVER] Invalid packet header")
            continue

        # ======================================
        # START TRANSFER
        # ======================================

        if packet_type == START:

            # Repeat START from the same transfer:
            # resend handshake ACK instead of resetting data.
            if (
                packet_transfer_id == transfer_id
                and address == client_address
                and metadata is not None
            ):

                server.sendto(
                    create_packet(
                        ACK,
                        transfer_id,
                        START_ACK_SEQ,
                        total_packets
                    ),
                    address
                )

                continue

            try:

                new_metadata = decode_metadata(payload)

                filename = new_metadata["filename"]
                file_size = new_metadata["file_size"]
                packet_count = new_metadata["total_packets"]
                chunk_size = new_metadata["chunk_size"]
                file_hash = new_metadata["sha256"]

                if not isinstance(filename, str):
                    raise ValueError("Invalid filename")

                if not isinstance(file_size, int) or file_size < 0:
                    raise ValueError("Invalid file size")

                if not isinstance(packet_count, int):
                    raise ValueError("Invalid packet count")

                if not 0 <= packet_count <= 1_000_000:
                    raise ValueError("Packet count outside allowed range")

                if chunk_size != 1000:
                    raise ValueError("Invalid chunk size")

                if not isinstance(file_hash, str):
                    raise ValueError("Invalid SHA256")

                if not re.fullmatch(r"[0-9a-f]{64}", file_hash):
                    raise ValueError("Invalid SHA256 format")

                expected_packets = (
                    (file_size + chunk_size - 1) // chunk_size
                )

                if packet_count != expected_packets:
                    raise ValueError("Packet count does not match file size")

                # Store the new transfer
                transfer_id = packet_transfer_id
                client_address = address
                metadata = new_metadata

                total_packets = packet_count

                received_packets = {}
                completed = False

                print("\n" + "=" * 60)
                print("[SERVER] NEW FILE TRANSFER")
                print("=" * 60)

                print(f"[SERVER] File: {filename}")
                print(f"[SERVER] Size: {file_size} bytes")
                print(f"[SERVER] Packets: {total_packets}")

                # Confirm that the server is ready
                server.sendto(
                    create_packet(
                        ACK,
                        transfer_id,
                        START_ACK_SEQ,
                        total_packets
                    ),
                    address
                )

                print("[SERVER] Transfer initialization ACK sent")

            except (
                ValueError,
                KeyError,
                TypeError
            ) as error:

                print("[SERVER] Invalid metadata:", error)

                server.sendto(
                    create_packet(
                        ERROR,
                        packet_transfer_id,
                        0,
                        0,
                        str(error).encode()
                    ),
                    address
                )

            continue

        # ======================================
        # VALIDATE ACTIVE TRANSFER
        # ======================================

        if (
            transfer_id is None
            or packet_transfer_id != transfer_id
            or address != client_address
            or metadata is None
        ):

            continue

        # ======================================
        # RECEIVE DATA PACKETS
        # ======================================

        if packet_type == DATA:

            if total != total_packets:
                continue

            if not 0 <= sequence < total_packets:
                continue

            if len(payload) == 0 or len(payload) > 1000:
                continue

            expected_length = min(
                1000,
                metadata["file_size"] - sequence * 1000
            )

            if len(payload) != expected_length:
                continue

            if sequence in received_packets:

                print(
                    f"[SERVER] Duplicate packet {sequence} ignored"
                )

            else:

                received_packets[sequence] = payload

                print(
                    f"[SERVER] Received packet "
                    f"{sequence + 1}/{total_packets}"
                )

            # ACK is sent even for duplicate packets.
            server.sendto(
                create_packet(
                    ACK,
                    transfer_id,
                    sequence,
                    total_packets
                ),
                address
            )

        # ======================================
        # FINISH TRANSFER
        # ======================================

        elif packet_type == FIN:

            if total != total_packets:
                continue

            if completed:

                # Allow repeated FIN packets to receive DONE.
                server.sendto(
                    create_packet(
                        DONE,
                        transfer_id,
                        0,
                        total_packets
                    ),
                    address
                )

                continue

            missing = [
                i for i in range(total_packets)
                if i not in received_packets
            ]

            if missing:

                print(
                    f"[SERVER] Missing {len(missing)} packets"
                )

                server.sendto(
                    create_packet(
                        ERROR,
                        transfer_id,
                        0,
                        total_packets,
                        b"Missing packets"
                    ),
                    address
                )

                continue

            # Reconstruct the file in sequence order
            file_data = b"".join(
                received_packets[i]
                for i in range(total_packets)
            )

            # Verify file size
            if len(file_data) != metadata["file_size"]:

                server.sendto(
                    create_packet(
                        ERROR,
                        transfer_id,
                        0,
                        total_packets,
                        b"File size mismatch"
                    ),
                    address
                )

                continue

            # Verify SHA256
            received_hash = calculate_sha256(file_data)

            if received_hash != metadata["sha256"]:

                server.sendto(
                    create_packet(
                        ERROR,
                        transfer_id,
                        0,
                        total_packets,
                        b"SHA256 verification failed"
                    ),
                    address
                )

                continue

            # Sanitize filename
            filename = os.path.basename(
                metadata["filename"]
            )

            if not filename or filename in (".", ".."):
                filename = "received_file.bin"

            # Add a transfer-specific suffix to avoid overwriting
            name, extension = os.path.splitext(filename)

            output_filename = (
                f"{name}_{transfer_id.hex()[:8]}{extension}"
            )

            output_path = os.path.join(
                OUTPUT_DIR,
                output_filename
            )

            with open(output_path, "wb") as file:

                file.write(file_data)

            completed = True

            print("\n" + "=" * 60)
            print("[SERVER] FILE TRANSFER SUCCESSFUL")
            print("=" * 60)

            print(f"[SERVER] Saved file: {output_path}")
            print(f"[SERVER] Packets received: {len(received_packets)}")
            print(f"[SERVER] SHA256: {received_hash}")
            print("[SERVER] FILE INTEGRITY: VERIFIED")

            # Confirm completion
            server.sendto(
                create_packet(
                    DONE,
                    transfer_id,
                    0,
                    total_packets
                ),
                address
            )

            print("[SERVER] Completion ACK sent\n")

if __name__ == "__main__":

    try:

        start_server()

    except KeyboardInterrupt:

        print("\n[SERVER] Shutting down")
