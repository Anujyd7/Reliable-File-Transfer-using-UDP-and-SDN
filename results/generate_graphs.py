import csv
import os
import matplotlib.pyplot as plt

# --------------------------------------------------
# PATH CONFIGURATION
# --------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_FILE = os.path.join(BASE_DIR, "performance_results.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "graphs")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------
# READ PERFORMANCE DATA
# --------------------------------------------------

data = []

with open(CSV_FILE, "r", newline="") as file:
    reader = csv.DictReader(file)

    for row in reader:
        data.append({
            "size": row["File Size"],
            "condition": row["Network Condition"],
            "time": float(row["Transfer Time (seconds)"]),
            "throughput": float(row["Throughput (Mbps)"]),
            "retransmissions": int(row["Retransmissions"]),
            "integrity": row["Integrity"]
        })

if not data:
    raise SystemExit("No performance data found.")

# --------------------------------------------------
# GRAPH 1: TRANSFER TIME
# --------------------------------------------------

plt.figure(figsize=(9, 5))

for condition in sorted(set(d["condition"] for d in data)):
    subset = [d for d in data if d["condition"] == condition]

    plt.plot(
        [d["size"] for d in subset],
        [d["time"] for d in subset],
        marker="o",
        linewidth=2,
        label=condition
    )

    for d in subset:
        plt.annotate(
            f'{d["time"]:.3f}s',
            (d["size"], d["time"]),
            xytext=(5, 7),
            textcoords="offset points"
        )

plt.xlabel("File Size")
plt.ylabel("Transfer Time (seconds)")
plt.title("File Transfer Time Comparison")
plt.grid(True)
plt.legend()
plt.tight_layout()

plt.savefig(
    os.path.join(OUTPUT_DIR, "transfer_time.png"),
    dpi=300
)

plt.close()

# --------------------------------------------------
# GRAPH 2: THROUGHPUT
# --------------------------------------------------

plt.figure(figsize=(9, 5))

for condition in sorted(set(d["condition"] for d in data)):
    subset = [d for d in data if d["condition"] == condition]

    plt.plot(
        [d["size"] for d in subset],
        [d["throughput"] for d in subset],
        marker="o",
        linewidth=2,
        label=condition
    )

    for d in subset:
        plt.annotate(
            f'{d["throughput"]:.3f} Mbps',
            (d["size"], d["throughput"]),
            xytext=(5, 7),
            textcoords="offset points"
        )

plt.xlabel("File Size")
plt.ylabel("Throughput (Mbps)")
plt.title("Network Throughput Comparison")
plt.grid(True)
plt.legend()
plt.tight_layout()

plt.savefig(
    os.path.join(OUTPUT_DIR, "throughput.png"),
    dpi=300
)

plt.close()

# --------------------------------------------------
# GRAPH 3: RETRANSMISSIONS
# --------------------------------------------------

plt.figure(figsize=(9, 5))

labels = [
    f'{d["size"]}\n{d["condition"]}'
    for d in data
]

values = [
    d["retransmissions"]
    for d in data
]

bars = plt.bar(labels, values)

plt.xlabel("File Size and Network Condition")
plt.ylabel("Number of Retransmissions")
plt.title("Packet Retransmission Comparison")
plt.grid(axis="y")

for bar, value in zip(bars, values):
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height(),
        str(value),
        ha="center",
        va="bottom"
    )

plt.tight_layout()

plt.savefig(
    os.path.join(OUTPUT_DIR, "retransmissions.png"),
    dpi=300
)

plt.close()

# --------------------------------------------------
# GRAPH 4: INTEGRITY VERIFICATION
# --------------------------------------------------

plt.figure(figsize=(9, 5))

labels = [d["size"] for d in data]
passed = [1 if d["integrity"].strip().upper() == "PASSED" else 0
          for d in data]

plt.bar(labels, passed)

plt.xlabel("File Size")
plt.ylabel("Integrity Status (1 = Passed, 0 = Failed)")
plt.title("File Integrity Verification")
plt.yticks([0, 1], ["Failed", "Passed"])
plt.ylim(0, 1.2)
plt.grid(axis="y")

plt.tight_layout()

plt.savefig(
    os.path.join(OUTPUT_DIR, "integrity_verification.png"),
    dpi=300
)

plt.close()

# --------------------------------------------------
# PRINT SUMMARY
# --------------------------------------------------

print("\n========================================")
print(" PERFORMANCE EVALUATION COMPLETED")
print("========================================")

for d in data:
    print(f'\nFile Size: {d["size"]}')
    print(f'Network: {d["condition"]}')
    print(f'Transfer Time: {d["time"]} seconds')
    print(f'Throughput: {d["throughput"]} Mbps')
    print(f'Retransmissions: {d["retransmissions"]}')
    print(f'Integrity: {d["integrity"]}')

print("\nGraphs saved in:")
print(OUTPUT_DIR)

print("\nGenerated graphs:")
print("1. transfer_time.png")
print("2. throughput.png")
print("3. retransmissions.png")
print("4. integrity_verification.png")
