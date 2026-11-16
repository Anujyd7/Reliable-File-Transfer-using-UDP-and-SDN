import socket
import struct
import os
import sys
import time
import hashlib

SERVER_HOST = "10.0.0.2"
SERVER_PORT = 5001

CHUNK_SIZE = 1000

HEADER = struct.Struct("!4sIII")
MAGIC = b"BASE"
END_SEQUENCE = 0xFFFFFFFF


def calculate_sha256(filename):
    sha256 = hashlib.sha256()

    with open(filename, "rb") as file:
        while True:
            data = file.read(65536)
            if not data:
                break
            sha256.update(data)

    return sha256.hexdigest()


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 -m baseline.udp_baseline_client <file>")
        return

    filename = sys.argv[1]

    if not os.path.isfile(filename):
        print("Error: Input file not found.")
        return

    file_size = os.path.getsize(filename)
    total_chunks = (file_size + CHUNK_SIZE - 1) // CHUNK_SIZE

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print("========== BASIC UDP BASELINE ==========")
    print(f"File: {filename}")
    print(f"File size: {file_size} bytes")
    print(f"Total packets: {total_chunks}")
    print(f"Server: {SERVER_HOST}:{SERVER_PORT}")

    start_time = time.time()

    with open(filename, "rb") as file:
        for sequence in range(total_chunks):
            data = file.read(CHUNK_SIZE)

            header = HEADER.pack(
                MAGIC,
                total_chunks,
                file_size,
                sequence
            )

            sock.sendto(header + data, (SERVER_HOST, SERVER_PORT))

    # Send one end-of-transfer marker.
    end_packet = HEADER.pack(
        MAGIC,
        total_chunks,
        file_size,
        END_SEQUENCE
    )

    sock.sendto(end_packet, (SERVER_HOST, SERVER_PORT))

    elapsed = time.time() - start_time
    sock.close()

    throughput = (
        (file_size * 8) / elapsed / 1_000_000
        if elapsed > 0 else 0
    )

    print("\n========== CLIENT RESULTS ==========")
    print(f"Packets sent: {total_chunks}")
    print(f"Transfer time: {elapsed:.3f} seconds")
    print(f"Throughput: {throughput:.3f} Mbps")
    print("Retransmissions: 0")
    print("Application ACKs: 0")
    print("SHA-256 of source:", calculate_sha256(filename))
    print("===================================")


if __name__ == "__main__":
    main()
