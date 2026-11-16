import socket
import struct
import hashlib
import os
import time

HOST = "0.0.0.0"
PORT = 5001

OUTPUT_DIR = "received_files"
OUTPUT_FILE = "baseline_received.bin"

HEADER = struct.Struct("!4sIII")
MAGIC = b"BASE"

END_SEQUENCE = 0xFFFFFFFF
BUFFER_SIZE = 2048


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
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.settimeout(2.0)

    print(f"Basic UDP baseline server listening on {HOST}:{PORT}")
    print("Waiting for file packets...")

    packets = {}
    total_chunks = None
    file_size = None
    start_time = None
    end_time = None
    client_address = None
    end_received = False

    try:
        while True:
            try:
                packet, address = server.recvfrom(BUFFER_SIZE)

            except socket.timeout:
                if end_received or packets:
                    break
                continue

            if len(packet) < HEADER.size:
                continue

            magic, chunks, size, sequence = HEADER.unpack(
                packet[:HEADER.size]
            )

            if magic != MAGIC:
                continue

            if total_chunks is None:
                total_chunks = chunks
                file_size = size
                client_address = address
                start_time = time.time()

                print(f"Receiving from {address}")
                print(f"Expected chunks: {total_chunks}")
                print(f"Expected file size: {file_size} bytes")

            if address != client_address:
                continue

            if chunks != total_chunks or size != file_size:
                continue

            if sequence == END_SEQUENCE:
                end_time = time.time()
                end_received = True

                # Briefly allow any reordered data packets to arrive.
                server.settimeout(0.1)
                continue

            if sequence >= total_chunks:
                continue

            packets[sequence] = packet[HEADER.size:]

    except KeyboardInterrupt:
        print("\nServer interrupted.")

    finally:
        server.close()

    if total_chunks is None:
        print("No valid file packets received.")
        return

    received_count = len(packets)
    missing_count = total_chunks - received_count

    output_path = os.path.join(OUTPUT_DIR, OUTPUT_FILE)

    with open(output_path, "wb") as output:
        for sequence in range(total_chunks):
            if sequence in packets:
                output.write(packets[sequence])

    received_size = os.path.getsize(output_path)

    if end_time is not None:
        elapsed = end_time - start_time
    else:
        elapsed = time.time() - start_time

    print("\n========== BASELINE UDP RESULTS ==========")
    print(f"Packets expected: {total_chunks}")
    print(f"Packets received: {received_count}")
    print(f"Packets missing: {missing_count}")
    print(f"Expected file size: {file_size} bytes")
    print(f"Received file size: {received_size} bytes")
    print(f"Reception time: {elapsed:.3f} seconds")

    if missing_count == 0 and received_size == file_size:
        print("Transfer status: COMPLETE")
    else:
        print("Transfer status: INCOMPLETE")

    print("SHA-256:", calculate_sha256(output_path))
    print("==========================================")


if __name__ == "__main__":
    main()
