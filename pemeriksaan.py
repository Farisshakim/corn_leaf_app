import hashlib
import tkinter as tk

from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Event
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image


EKSTENSI = {
    ".jpg", ".jpeg", ".png",
    ".bmp", ".tif", ".tiff", ".webp"
}


def hash_file(path):
    """Sidik digital isi file, tanpa bergantung pada nama file."""
    hasil = hashlib.sha256()

    with path.open("rb") as file:
        for blok in iter(lambda: file.read(1024 * 1024), b""):
            hasil.update(blok)

    return hasil.hexdigest()


class JendelaPemeriksaan:
    def __init__(self, parent, folder_dataset):
        self.folder = Path(folder_dataset)
        self.antrean = Queue()
        self.berhenti = Event()
        self.ditutup = False

        self.window = tk.Toplevel(parent)
        self.window.title("Pemeriksaan Dataset")
        self.window.geometry("950x650")

        # Jendela utama tidak bisa diubah saat pemeriksaan.
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.tutup)

        frame = ttk.Frame(self.window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Pemeriksaan File dan Duplikat",
            font=("", 17, "bold")
        ).pack(anchor=tk.W)

        ttk.Label(
            frame,
            text=f"Dataset: {self.folder}",
            wraplength=900
        ).pack(anchor=tk.W, pady=8)

        self.status = tk.StringVar(value="Menyiapkan pemeriksaan...")

        ttk.Label(
            frame,
            textvariable=self.status
        ).pack(anchor=tk.W, pady=5)

        self.progress = ttk.Progressbar(
            frame,
            mode="determinate"
        )
        self.progress.pack(fill=tk.X, pady=8)

        self.teks = ScrolledText(
            frame,
            wrap=tk.WORD,
            font=("Menlo", 11),
            state=tk.DISABLED
        )
        self.teks.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text=(
                "Tidak ada file yang dihapus atau diubah. "
                "Duplikat persis diperiksa berdasarkan isi file."
            ),
            wraplength=900
        ).pack(anchor=tk.W, pady=10)

        ttk.Button(
            frame,
            text="Tutup / Hentikan",
            command=self.tutup
        ).pack(anchor=tk.E)

        self.window.after(100, self.periksa_antrean)

        Thread(
            target=self.proses,
            daemon=True
        ).start()

    def tulis(self, pesan):
        self.teks.configure(state=tk.NORMAL)
        self.teks.insert(tk.END, pesan + "\n")
        self.teks.configure(state=tk.DISABLED)

    def proses(self):
        """Berjalan di thread terpisah, tanpa mengakses widget GUI."""
        try:
            if not self.folder.is_dir():
                raise ValueError("Folder dataset tidak ditemukan.")

            daftar = []

            for path in self.folder.rglob("*"):
                if self.berhenti.is_set():
                    return

                relatif = path.relative_to(self.folder)

                if any(
                    bagian.startswith(".") or bagian == "__MACOSX"
                    for bagian in relatif.parts
                ):
                    continue

                # Hanya gambar di dalam folder kategori.
                if len(relatif.parts) < 2:
                    continue

                if path.is_file() and path.suffix.lower() in EKSTENSI:
                    daftar.append(path)

            daftar.sort(key=lambda path: str(path).lower())
            total = len(daftar)

            self.antrean.put(("mulai", total))

            kelompok_hash = {}
            gagal = []
            terbaca = 0

            for nomor, path in enumerate(daftar, start=1):
                if self.berhenti.is_set():
                    return

                relatif = str(path.relative_to(self.folder))

                # Pemeriksaan hash dipisahkan dari pemeriksaan gambar,
                # sehingga file rusak pun dapat teridentifikasi sebagai
                # salinan persis jika isi filenya dapat dibaca.
                masalah = []

                try:
                    sidik = hash_file(path)
                    kelompok_hash.setdefault(sidik, []).append(path)
                except Exception as error:
                    masalah.append(f"Gagal membaca isi file: {error}")

                try:
                    with Image.open(path) as gambar:
                        gambar.verify()

                    # Buka kembali setelah verify untuk membaca piksel.
                    with Image.open(path) as gambar:
                        for frame in range(
                            getattr(gambar, "n_frames", 1)
                        ):
                            gambar.seek(frame)
                            gambar.load()

                    terbaca += 1

                except Exception as error:
                    masalah.append(
                        f"Gagal validasi gambar: "
                        f"{type(error).__name__}: {error}"
                    )

                if masalah:
                    gagal.append((relatif, " | ".join(masalah)))

                self.antrean.put(
                    ("progres", (nomor, total))
                )

            duplikat = [
                anggota
                for anggota in kelompok_hash.values()
                if len(anggota) > 1
            ]

            self.antrean.put(
                (
                    "selesai",
                    {
                        "total": total,
                        "terbaca": terbaca,
                        "gagal": gagal,
                        "duplikat": duplikat
                    }
                )
            )

        except Exception as error:
            self.antrean.put(("error", str(error)))

    def periksa_antrean(self):
        if self.ditutup:
            return

        # Batasi jumlah pesan agar GUI tetap responsif.
        for _ in range(100):
            try:
                jenis, data = self.antrean.get_nowait()
            except Empty:
                break

            if jenis == "mulai":
                self.progress.configure(maximum=max(data, 1))
                self.tulis(f"Ditemukan {data} file gambar.\n")

            elif jenis == "progres":
                nomor, total = data
                self.progress["value"] = nomor
                self.status.set(
                    f"Memeriksa {nomor} dari {total} gambar..."
                )

            elif jenis == "selesai":
                self.tampilkan_hasil(data)

            elif jenis == "error":
                self.status.set("Pemeriksaan gagal.")
                self.tulis(f"ERROR: {data}")

        self.window.after(100, self.periksa_antrean)

    def tampilkan_hasil(self, hasil):
        duplikat = hasil["duplikat"]

        # Jumlah salinan di luar satu file per kelompok.
        salinan_tambahan = sum(
            len(anggota) - 1 for anggota in duplikat
        )

        self.status.set("Pemeriksaan selesai.")

        self.tulis("RINGKASAN")
        self.tulis(f"Total diperiksa: {hasil['total']}")
        self.tulis(f"Gambar berhasil dibaca: {hasil['terbaca']}")
        self.tulis(
            f"File mengalami kegagalan pemeriksaan: "
            f"{len(hasil['gagal'])}"
        )
        self.tulis(f"Kelompok duplikat persis: {len(duplikat)}")
        self.tulis(f"Salinan tambahan: {salinan_tambahan}")

        self.tulis("\nFILE YANG PERLU DITINJAU")

        if not hasil["gagal"]:
            self.tulis("Tidak ditemukan kegagalan pemeriksaan.")

        for nama, alasan in hasil["gagal"]:
            self.tulis(f"\n{nama}\n  Alasan: {alasan}")

        self.tulis("\nKELOMPOK DUPLIKAT PERSIS")

        if not duplikat:
            self.tulis("Tidak ditemukan duplikat dengan isi file identik.")

        for nomor, anggota in enumerate(duplikat, start=1):
            kategori = {
                path.relative_to(self.folder).parts[0]
                for path in anggota
            }

            lintas_kategori = len(kategori) > 1

            keterangan = (
                "LINTAS KATEGORI — periksa kebenaran label"
                if lintas_kategori
                else "Dalam kategori yang sama"
            )

            self.tulis(f"\nKelompok {nomor}: {keterangan}")

            for path in anggota:
                self.tulis(
                    f"  - {path.relative_to(self.folder)}"
                )

        self.tulis(
            "\nCatatan: gambar yang dikompresi ulang, diubah "
            "ukurannya, atau dipotong belum terdeteksi oleh "
            "pemeriksaan duplikat persis ini."
        )

        self.tulis(
            "Hasil berhasil dibaca tidak menjamin gambar "
            "tajam, label benar, atau lesi terlihat jelas."
        )

    def tutup(self):
        self.ditutup = True
        self.berhenti.set()
        self.window.destroy()