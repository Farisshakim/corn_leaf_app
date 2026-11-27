import json
import hashlib
import tkinter as tk

from datetime import datetime, timezone
from pathlib import Path
from tkinter import ttk, messagebox

from PIL import Image, ImageOps, ImageTk


EKSTENSI = {
    ".jpg", ".jpeg", ".png",
    ".bmp", ".tif", ".tiff", ".webp"
}

STATUS = {
    "layak": "Layak",
    "tinjau": "Perlu ditinjau",
    "tidak_layak": "Tidak layak"
}


class JendelaKualitas:
    def __init__(self, parent, folder_dataset):
        self.folder = Path(folder_dataset).resolve()
        self.daftar = []
        self.indeks = 0
        self.catatan = {}
        self.gagal_memuat = None
        self.identitas_tampil = None

        identitas = hashlib.sha256(
            str(self.folder).encode("utf-8")
        ).hexdigest()[:12]

        self.file_laporan = (
            Path(__file__).resolve().parent
            / "laporan"
            / f"kualitas_{identitas}.json"
        )

        self.window = tk.Toplevel(parent)
        self.window.title("Pemeriksaan Kualitas Dataset")
        self.window.geometry("1000x800")
        self.window.transient(parent)
        self.window.grab_set()

        self.info = tk.StringVar()
        self.status_var = tk.StringVar()
        self.ringkasan = tk.StringVar()
        self.alasan = tk.StringVar()

        self.muat_laporan()
        self.buat_tampilan()

        try:
            if not self.folder.is_dir():
                raise ValueError("Folder dataset tidak ditemukan.")

            for path in self.folder.rglob("*"):
                relatif = path.relative_to(self.folder)

                if len(relatif.parts) < 2:
                    continue

                if any(
                    bagian.startswith(".") or bagian == "__MACOSX"
                    for bagian in relatif.parts
                ):
                    continue

                if path.is_file() and path.suffix.lower() in EKSTENSI:
                    self.daftar.append(path)

            self.daftar.sort(
                key=lambda path: str(path).lower()
            )

        except Exception as error:
            messagebox.showerror(
                "Gagal membaca dataset",
                str(error),
                parent=self.window
            )

        self.perbarui_ringkasan()

        if self.daftar:
            self.tampilkan()
        else:
            self.info.set("Tidak ada gambar yang dapat ditampilkan.")
            self.status_var.set("Periksa lokasi folder dataset.")

    def muat_laporan(self):
        if not self.file_laporan.exists():
            return

        try:
            data = json.loads(
                self.file_laporan.read_text(encoding="utf-8")
            )

            if not isinstance(data, dict):
                raise ValueError("Format laporan tidak valid.")

            catatan = data.get("catatan")

            if not isinstance(catatan, dict):
                raise ValueError("Bagian catatan tidak valid.")

            for item in catatan.values():
                if (
                    not isinstance(item, dict)
                    or item.get("status") not in STATUS
                    or not isinstance(item.get("alasan", ""), str)
                    or not isinstance(item.get("identitas"), dict)
                ):
                    raise ValueError("Ada catatan yang tidak valid.")

            self.catatan = catatan

        except Exception as error:
            self.gagal_memuat = str(error)

    def buat_tampilan(self):
        frame = ttk.Frame(self.window, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Pemeriksaan Kualitas Gambar",
            font=("", 17, "bold")
        ).pack(anchor=tk.W)

        ttk.Label(
            frame,
            textvariable=self.ringkasan,
            wraplength=950
        ).pack(anchor=tk.W, pady=8)

        ttk.Label(
            frame,
            textvariable=self.info,
            wraplength=950
        ).pack(anchor=tk.W)

        self.preview = ttk.Label(
            frame,
            anchor=tk.CENTER
        )
        self.preview.pack(
            fill=tk.BOTH,
            expand=True,
            pady=10
        )

        ttk.Label(
            frame,
            textvariable=self.status_var,
            wraplength=950
        ).pack(anchor=tk.W, pady=5)

        ttk.Label(
            frame,
            text="Alasan / catatan (wajib untuk tinjau atau tidak layak):"
        ).pack(anchor=tk.W)

        ttk.Entry(
            frame,
            textvariable=self.alasan
        ).pack(fill=tk.X, pady=(5, 10))

        keputusan = ttk.Frame(frame)
        keputusan.pack(fill=tk.X)

        self.tombol_status = []

        for nilai, nama in STATUS.items():
            tombol = ttk.Button(
                keputusan,
                text=nama,
                command=lambda status=nilai: self.simpan(status),
                state=tk.DISABLED
            )
            tombol.pack(side=tk.LEFT, padx=(0, 8))
            self.tombol_status.append(tombol)

        navigasi = ttk.Frame(frame)
        navigasi.pack(fill=tk.X, pady=12)

        self.prev = ttk.Button(
            navigasi,
            text="← Sebelumnya",
            command=lambda: self.pindah(-1),
            state=tk.DISABLED
        )
        self.prev.pack(side=tk.LEFT)

        self.next = ttk.Button(
            navigasi,
            text="Berikutnya →",
            command=lambda: self.pindah(1),
            state=tk.DISABLED
        )
        self.next.pack(side=tk.LEFT, padx=8)

        ttk.Button(
            navigasi,
            text="Ke Gambar Belum Dinilai",
            command=self.cari_belum_dinilai
        ).pack(side=tk.LEFT)

        ttk.Button(
            navigasi,
            text="Tutup",
            command=self.window.destroy
        ).pack(side=tk.RIGHT)

        ttk.Label(
            frame,
            text=(
                "Klik keputusan untuk menyimpan. "
                "Pratinjau diperkecil; gambar asli tidak diubah. "
                "Status tidak layak belum menghapus atau memindahkan file."
            ),
            wraplength=950
        ).pack(anchor=tk.W)

    def identitas_file(self, path):
        info = path.stat()

        return {
            "ukuran_bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns
        }

    def catatan_aktif(self, path):
        nama = str(path.relative_to(self.folder))
        catatan = self.catatan.get(nama)

        if not catatan:
            return None

        try:
            if catatan["identitas"] == self.identitas_file(path):
                return catatan
        except OSError:
            pass

        return None

    def tampilkan(self):
        path = self.daftar[self.indeks]
        relatif = path.relative_to(self.folder)

        self.identitas_tampil = None

        for tombol in self.tombol_status:
            tombol.configure(state=tk.DISABLED)

        try:
            identitas_awal = self.identitas_file(path)

            with Image.open(path) as sumber:
                gambar = ImageOps.exif_transpose(sumber).convert("RGB")
                lebar, tinggi = gambar.size

                gambar.thumbnail(
                    (850, 420),
                    Image.Resampling.LANCZOS
                )

            if identitas_awal != self.identitas_file(path):
                raise ValueError("File berubah saat dibaca. Buka ulang gambar.")

            foto = ImageTk.PhotoImage(
                gambar,
                master=self.window
            )

            self.preview.configure(image=foto, text="")
            self.preview.image = foto
            self.identitas_tampil = identitas_awal

            self.info.set(
                f"Gambar {self.indeks + 1}/{len(self.daftar)} | "
                f"Kategori: {relatif.parts[0]}\n"
                f"{relatif} | Resolusi: {lebar} × {tinggi}"
            )

        except Exception as error:
            self.preview.configure(
                image="",
                text=f"Gagal menampilkan gambar:\n{error}"
            )
            self.preview.image = None
            self.info.set(str(relatif))

        catatan = self.catatan_aktif(path)

        if catatan:
            self.alasan.set(catatan.get("alasan", ""))
            self.status_var.set(
                f"Status tersimpan: {STATUS[catatan['status']]}"
            )
        else:
            self.alasan.set("")
            self.status_var.set(
                "Belum dinilai, atau file berubah sejak penilaian terakhir."
            )

        if self.gagal_memuat:
            self.status_var.set(
                "Penyimpanan diblokir: laporan lama gagal dibaca. "
                f"{self.gagal_memuat}"
            )
        else:
            # File gagal ditampilkan tetap dapat ditandai untuk ditinjau.
            for tombol in self.tombol_status:
                tombol.configure(state=tk.NORMAL)

        self.prev.configure(
            state=tk.NORMAL if self.indeks > 0 else tk.DISABLED
        )
        self.next.configure(
            state=(
                tk.NORMAL
                if self.indeks < len(self.daftar) - 1
                else tk.DISABLED
            )
        )

    def simpan(self, status):
        if not self.daftar or self.gagal_memuat:
            return

        alasan = self.alasan.get().strip()

        if status != "layak" and not alasan:
            messagebox.showwarning(
                "Alasan diperlukan",
                "Isi alasan sebelum memilih Perlu ditinjau atau Tidak layak.",
                parent=self.window
            )
            return

        if status == "layak" and self.identitas_tampil is None:
            messagebox.showwarning(
                "Gambar belum dapat dinilai layak",
                "Gambar gagal ditampilkan. Periksa file terlebih dahulu.",
                parent=self.window
            )
            return

        path = self.daftar[self.indeks]

        try:
            identitas = self.identitas_file(path)

            if (
                self.identitas_tampil is not None
                and identitas != self.identitas_tampil
            ):
                raise ValueError(
                    "File berubah setelah ditampilkan. "
                    "Buka ulang gambar sebelum menyimpan keputusan."
                )

            nama = str(path.relative_to(self.folder))
            catatan_baru = dict(self.catatan)

            catatan_baru[nama] = {
                "status": status,
                "alasan": alasan,
                "kategori": path.relative_to(self.folder).parts[0],
                "identitas": identitas,
                "waktu_utc": datetime.now(timezone.utc).isoformat()
            }

            data = {
                "versi": 1,
                "dataset": str(self.folder),
                "catatan": catatan_baru
            }

            self.file_laporan.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            sementara = self.file_laporan.with_suffix(".tmp")
            sementara.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            sementara.replace(self.file_laporan)

            self.catatan = catatan_baru
            self.status_var.set(f"Tersimpan: {STATUS[status]}")
            self.perbarui_ringkasan()

        except Exception as error:
            messagebox.showerror(
                "Gagal menyimpan",
                str(error),
                parent=self.window
            )

    def perbarui_ringkasan(self):
        jumlah = {status: 0 for status in STATUS}

        for path in self.daftar:
            catatan = self.catatan_aktif(path)

            if catatan:
                jumlah[catatan["status"]] += 1

        belum = len(self.daftar) - sum(jumlah.values())

        self.ringkasan.set(
            f"Layak: {jumlah['layak']} | "
            f"Perlu ditinjau: {jumlah['tinjau']} | "
            f"Tidak layak: {jumlah['tidak_layak']} | "
            f"Belum dinilai: {belum}"
        )

    def pindah(self, arah):
        tujuan = self.indeks + arah

        if 0 <= tujuan < len(self.daftar):
            self.indeks = tujuan
            self.tampilkan()

    def cari_belum_dinilai(self):
        if not self.daftar:
            return

        for langkah in range(1, len(self.daftar) + 1):
            posisi = (self.indeks + langkah) % len(self.daftar)

            if self.catatan_aktif(self.daftar[posisi]) is None:
                self.indeks = posisi
                self.tampilkan()
                return

        messagebox.showinfo(
            "Pemeriksaan",
            "Semua gambar sudah memiliki keputusan. "
            "Status Perlu ditinjau tetap membutuhkan pemeriksaan lanjutan.",
            parent=self.window
        )