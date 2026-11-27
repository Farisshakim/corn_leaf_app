import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from threading import Thread
from queue import Queue, Empty

from pemeriksaan import JendelaPemeriksaan
from kemiripan import JendelaKemiripan
from kualitas import JendelaKualitas

# Lokasi folder dataset berada di sebelah main.py.
FOLDER_PROYEK = Path(__file__).resolve().parent
FOLDER_DATASET = FOLDER_PROYEK / "dataset"

TARGET = 510
EKSTENSI_GAMBAR = {
    ".jpg", ".jpeg", ".png",
    ".bmp", ".tif", ".tiff", ".webp"
}


class AplikasiDataset:
    def __init__(self, root):
        self.root = root
        self.root.title("Pengelolaan Dataset Daun Jagung")
        self.root.geometry("900x520")
        self.root.minsize(750, 450)

        self.folder_dataset = FOLDER_DATASET
        self.antrean = Queue()
        self.sedang_memindai = False

        self.lokasi_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Menyiapkan aplikasi...")
        self.total_var = tk.StringVar(value="Total: 0 gambar")

        self.buat_tampilan()
        self.tombol_periksa.pack(side=tk.LEFT)

        # Periksa hasil pekerjaan latar belakang secara berkala.
        self.root.after(100, self.periksa_antrean)

        # Baca dataset otomatis ketika aplikasi dibuka.
        self.root.after(200, self.pindai_dataset)

    def buat_tampilan(self):
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Dataset Penyakit Daun Jagung",
            font=("", 18, "bold")
        ).pack(anchor=tk.W)

        ttk.Label(
            frame,
            text="Target: 510 gambar per kategori • 2.040 gambar total"
        ).pack(anchor=tk.W, pady=(5, 15))

        ttk.Label(
            frame,
            textvariable=self.lokasi_var,
            wraplength=830
        ).pack(anchor=tk.W, pady=(0, 12))

        bar_tombol = ttk.Frame(frame)
        bar_tombol.pack(fill=tk.X, pady=(0, 12))

        self.tombol_pindai = ttk.Button(
            bar_tombol,
            text="Pindai Ulang",
            command=self.pindai_dataset
        )
        self.tombol_pindai.pack(side=tk.LEFT)

        self.tombol_folder = ttk.Button(
            bar_tombol,
            text="Ganti Folder",
            command=self.pilih_folder
        )
        self.tombol_folder.pack(side=tk.LEFT, padx=10)
        bar_tinjauan = ttk.Frame(frame)
        bar_tinjauan.pack(fill=tk.X, pady=(0, 12))

        ttk.Button(
            bar_tinjauan,
            text="Tinjau Kualitas Gambar",
            command=lambda: JendelaKualitas(
                self.root,
                self.folder_dataset
            )
        ).pack(side=tk.LEFT)
        kolom = ("kategori", "jumlah", "target", "status")

        self.tabel = ttk.Treeview(
            frame,
            columns=kolom,
            show="headings",
            height=8
        )

        self.tombol_periksa = ttk.Button(
            bar_tombol,
            text="Periksa File & Duplikat",
            command=lambda: JendelaPemeriksaan(
                self.root,
                self.folder_dataset
            )
        )
        self.tombol_periksa.pack(side=tk.LEFT)

        self.tombol_mirip = ttk.Button(
            bar_tombol,
            text="Cari Gambar Mirip",
            command=lambda: JendelaKemiripan(
                self.root,
                self.folder_dataset
            )
        )
        self.tombol_mirip.pack(side=tk.LEFT, padx=8)

        self.tabel.heading("kategori", text="Folder Kategori")
        self.tabel.heading("jumlah", text="Jumlah Gambar")
        self.tabel.heading("target", text="Target")
        self.tabel.heading("status", text="Status Jumlah")

        self.tabel.column("kategori", width=240)
        self.tabel.column("jumlah", width=120, anchor=tk.CENTER)
        self.tabel.column("target", width=80, anchor=tk.CENTER)
        self.tabel.column("status", width=260)

        self.tabel.pack(fill=tk.BOTH, expand=True)

        self.progress = ttk.Progressbar(
            frame,
            mode="indeterminate"
        )
        self.progress.pack(fill=tk.X, pady=(15, 8))

        ttk.Label(
            frame,
            textvariable=self.total_var,
            font=("", 12, "bold")
        ).pack(anchor=tk.W)

        ttk.Label(
            frame,
            textvariable=self.status_var,
            wraplength=830
        ).pack(anchor=tk.W, pady=(8, 5))

        ttk.Label(
            frame,
            text=(
                "Tahap ini hanya menghitung file gambar. "
                "Kerusakan, duplikasi, dan kualitas belum diperiksa."
            ),
            wraplength=830
        ).pack(anchor=tk.W)

    def pilih_folder(self):
        lokasi = filedialog.askdirectory(
            title="Pilih folder induk empat kategori dataset"
        )

        if lokasi:
            self.folder_dataset = Path(lokasi)
            self.pindai_dataset()

    def pindai_dataset(self):
        if self.sedang_memindai:
            return

        self.lokasi_var.set(
            f"Lokasi dataset: {self.folder_dataset}"
        )

        for item in self.tabel.get_children():
            self.tabel.delete(item)

        self.total_var.set("Total: 0 gambar")

        if not self.folder_dataset.is_dir():
            self.status_var.set(
                "Folder dataset belum ditemukan. "
                "Letakkan folder 'dataset' di sebelah main.py "
                "atau klik Ganti Folder."
            )
            return

        self.sedang_memindai = True
        self.tombol_pindai.configure(state=tk.DISABLED)
        self.tombol_folder.configure(state=tk.DISABLED)

        self.status_var.set("Sedang menghitung file gambar...")
        self.progress.start(10)

        # Pemindaian berjalan terpisah agar jendela tidak membeku.
        Thread(
            target=self.proses_pemindaian,
            args=(self.folder_dataset,),
            daemon=True
        ).start()

    def proses_pemindaian(self, folder_dataset):
        try:
            kategori = sorted(
                (
                    folder
                    for folder in folder_dataset.iterdir()
                    if folder.is_dir()
                    and not folder.name.startswith(".")
                    and folder.name != "__MACOSX"
                ),
                key=lambda folder: folder.name.lower()
            )

            hasil = []

            for folder in kategori:
                jumlah = 0

                for file in folder.rglob("*"):
                    relatif = file.relative_to(folder)

                    # Abaikan file tersembunyi dan metadata macOS.
                    if any(
                        bagian.startswith(".")
                        or bagian == "__MACOSX"
                        for bagian in relatif.parts
                    ):
                        continue

                    if (
                        file.is_file()
                        and file.suffix.lower() in EKSTENSI_GAMBAR
                    ):
                        jumlah += 1

                hasil.append((folder.name, jumlah))

            self.antrean.put(("berhasil", hasil))

        except Exception as error:
            self.antrean.put(("gagal", str(error)))

    def periksa_antrean(self):
        try:
            jenis, data = self.antrean.get_nowait()
        except Empty:
            pass
        else:
            self.progress.stop()
            self.sedang_memindai = False

            self.tombol_pindai.configure(state=tk.NORMAL)
            self.tombol_folder.configure(state=tk.NORMAL)

            if jenis == "berhasil":
                self.tampilkan_hasil(data)
            else:
                self.status_var.set("Pemindaian gagal.")
                messagebox.showerror(
                    "Gagal Membaca Dataset",
                    data
                )

        self.root.after(100, self.periksa_antrean)

    def tampilkan_hasil(self, hasil):
        total = 0

        for nama, jumlah in hasil:
            total += jumlah

            if jumlah < TARGET:
                status = f"Kurang {TARGET - jumlah} gambar"
            elif jumlah == TARGET:
                status = "Sesuai target jumlah"
            else:
                status = f"Lebih {jumlah - TARGET} gambar"

            self.tabel.insert(
                "",
                tk.END,
                values=(nama, jumlah, TARGET, status)
            )

        self.total_var.set(
            f"Total: {total:,} gambar | "
            f"Folder kategori: {len(hasil)}"
        )

        if len(hasil) != 4:
            self.status_var.set(
                "Pemindaian selesai. Diharapkan ada empat folder "
                "kategori langsung di dalam folder dataset. "
                "Periksa kembali lokasi yang dipilih."
            )
        elif any(jumlah < TARGET for _, jumlah in hasil):
            self.status_var.set(
                "Pemindaian selesai. Ada kategori yang jumlah "
                "gambarnya belum mencapai 510."
            )
        else:
            self.status_var.set(
                "Pemindaian selesai. Semua kategori memiliki "
                "minimal 510 file gambar. Selanjutnya perlu "
                "pemeriksaan file rusak dan duplikasi."
            )


if __name__ == "__main__":
    root = tk.Tk()
    aplikasi = AplikasiDataset(root)
    root.mainloop()