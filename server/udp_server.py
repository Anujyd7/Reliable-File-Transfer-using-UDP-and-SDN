import socket
import os
import re

from protocol.reliability import (
    SERVER_PORT,
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

HOST = "0.0.0.0"
PORT = SERVER_PORT
OUTPUT_DIR = "received_files"

os.makedirs(OUTPUT_DIR, exist_ok=True)


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))

    # Each client transfer has its own independent state.
    sessions = {}

    print("=" * 60)
    print("       MULTI-CLIENT RELIABLE UDP FILE SERVER")
    print("=" * 60)
    print(f"[SERVER] Listening on {HOST}:{PORT}")
    print("[SERVER] Waiting for simultaneous client transfers...\n")

    try:
        while True:
            packet, address = server.recvfrom(MAX_DATAGRAM_SIZE)

            try:
                packet_type, transfer_id, sequence, total, payload = (
                    decode_packet(packet)
                )
            except ValueError:
                print("[SERVER] Invalid packet header")
                continue

            # A session is identified by both transfer ID and client address.
            session_key = (transfer_id, address)

            # ----------------------------------
            # START
            # ----------------------------------
            if packet_type == START:
                if session_key in sessions:
                    state = sessions[session_key]

                    server.sendto(
                        create_packet(
                            ACK, transfer_id,
                            START_ACK_SEQ, state["total_packets"]
                        ),
                        address
                    )
                    continue

                try:
                    metadata = decode_metadata(payload)

                    filename = metadata["filename"]
                    file_size = metadata["file_size"]
                    packet_count = metadata["total_packets"]
                    chunk_size = metadata["chunk_size"]
                    file_hash = metadata["sha256"]

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

                    if packet_count != expected_packets or total != packet_count:
                        raise ValueError("Packet count does not match file size")

                    sessions[session_key] = {
                        "metadata": metadata,
                        "total_packets": packet_count,
                        "received_packets": {},
                        "completed": False
                    }

                    print("\n" + "=" * 60)
                    print("[SERVER] NEW CLIENT TRANSFER")
                    print("=" * 60)
                    print(f"[SERVER] Client: {address}")
                    print(f"[SERVER] Transfer ID: {transfer_id.hex()[:8]}")
                    print(f"[SERVER] File: {filename}")
                    print(f"[SERVER] Size: {file_size} bytes")
                    print(f"[SERVER] Packets: {packet_count}")
                    print(f"[SERVER] Active sessions: {len(sessions)}")

                    server.sendto(
                        create_packet(
                            ACK, transfer_id,
                            START_ACK_SEQ, packet_count
                        ),
                        address
                    )

                except (ValueError, KeyError, TypeError) as error:
                    print("[SERVER] Invalid metadata:", error)
                    server.sendto(
                        create_packet(
                            ERROR, transfer_id, 0, 0, str(error).encode()
                        ),
                        address
                    )

                continue

            # ----------------------------------
            # VALIDATE SESSION
            # ----------------------------------
            state = sessions.get(session_key)

            if state is None:
                continue

            metadata = state["metadata"]
            total_packets = state["total_packets"]
            received_packets = state["received_packets"]

            # ----------------------------------
            # DATA
            # ----------------------------------
            if packet_type == DATA:
                if state["completed"]:
                    continue

                if total != total_packets:
                    continue

                if not 0 <= sequence < total_packets:
                    continue

                if not payload or len(payload) > 1000:
                    continue

                expected_length = min(
                    1000,
                    metadata["file_size"] - sequence * 1000
                )

                if len(payload) != expected_length:
                    continue

                if sequence not in received_packets:
                    received_packets[sequence] = payload

                # ACK both new and duplicate packets.
                server.sendto(
                    create_packet(
                        ACK, transfer_id, sequence, total_packets
                    ),
                    address
                )

            # ----------------------------------
            # FIN
            # ----------------------------------
            elif packet_type == FIN:
                if total != total_packets:
                    continue

                if state["completed"]:
                    server.sendto(
                        create_packet(
                            DONE, transfer_id, 0, total_packets
                        ),
                        address
                    )
                    continue

                missing = [
                    i for i in range(total_packets)
                    if i not in received_packets
                ]

                if missing:
                    server.sendto(
                        create_packet(
                            ERROR, transfer_id, 0,
                            total_packets, b"Missing packets"
                        ),
                        address
                    )
                    print(
                        f"[SERVER] Transfer {transfer_id.hex()[:8]} "
                        f"has {len(missing)} missing packets"
                    )
                    continue

                file_data = b"".join(
                    received_packets[i]
                    for i in range(total_packets)
                )

                if len(file_data) != metadata["file_size"]:
                    server.sendto(
                        create_packet(
                            ERROR, transfer_id, 0,
                            total_packets, b"File size mismatch"
                        ),
                        address
                    )
                    continue

                received_hash = calculate_sha256(file_data)

                if received_hash != metadata["sha256"]:
                    server.sendto(
                        create_packet(
                            ERROR, transfer_id, 0,
                            total_packets, b"SHA256 verification failed"
                        ),
                        address
                    )
                    continue

                filename = os.path.basename(metadata["filename"])

                if not filename or filename in (".", ".."):
                    filename = "received_file.bin"

                name, extension = os.path.splitext(filename)

                output_filename = (
                    f"{name}_{transfer_id.hex()[:8]}{extension}"
                )

                output_path = os.path.join(
                    OUTPUT_DIR, output_filename
                )

                with open(output_path, "wb") as file:
                    file.write(file_data)

                state["completed"] = True

                print("\n" + "=" * 60)
                print("[SERVER] FILE TRANSFER SUCCESSFUL")
                print("=" * 60)
                print(f"[SERVER] Client: {address}")
                print(f"[SERVER] File: {output_path}")
                print(f"[SERVER] Packets received: {len(received_packets)}")
                print(f"[SERVER] SHA256: {received_hash}")
                print("[SERVER] FILE INTEGRITY: VERIFIED")

                server.sendto(
                    create_packet(
                        DONE, transfer_id, 0, total_packets
                    ),
                    address
                )

                print("[SERVER] Completion ACK sent")
                print(
                    f"[SERVER] Active sessions: {len(sessions)}\n"
                )

    finally:
        server.close()


if __name__ == "__main__":
    try:
        start_server()
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down")
