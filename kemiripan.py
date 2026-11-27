import hashlib
import json
import tkinter as tk

from datetime import datetime, timezone
from pathlib import Path
from queue import Queue, Empty
from threading import Thread, Event
from tkinter import ttk, messagebox

from PIL import Image, ImageOps, ImageTk


EKSTENSI = {
    ".jpg", ".jpeg", ".png",
    ".bmp", ".tif", ".tiff", ".webp"
}

NAMA_STATUS = {
    "terkait": "Duplikat / daun yang sama",
    "berbeda": "Gambar berbeda",
    "tinjau": "Perlu ditinjau"
}


def hitung_dhash(path):
    """Ringkasan pola terang-gelap gambar dalam 64 bit."""
    with Image.open(path) as sumber:
        gambar = ImageOps.exif_transpose(sumber).convert("L")
        gambar = gambar.resize(
            (9, 8),
            Image.Resampling.LANCZOS
        )

        piksel = list(gambar.getdata())

    nilai = 0

    for y in range(8):
        for x in range(8):
            kiri = piksel[y * 9 + x]
            kanan = piksel[y * 9 + x + 1]
            nilai = (nilai << 1) | int(kiri > kanan)

    return nilai


class JendelaKemiripan:
    def __init__(self, parent, folder_dataset):
        self.folder = Path(folder_dataset).resolve()

        self.antrean = Queue()
        self.berhenti = Event()
        self.ditutup = False
        self.sedang_memproses = False

        self.pasangan = []
        self.indeks = 0
        self.keputusan = {}
        self.gagal_memuat = None

        # Lokasi penyimpanan hasil tinjauan.
        identitas_dataset = hashlib.sha256(
            str(self.folder).encode("utf-8")
        ).hexdigest()[:12]

        self.folder_laporan = (
            Path(__file__).resolve().parent / "laporan"
        )

        self.file_keputusan = (
            self.folder_laporan
            / f"tinjauan_kemiripan_{identitas_dataset}.json"
        )

        self.muat_keputusan()

        # Jendela GUI.
        self.window = tk.Toplevel(parent)
        self.window.title("Tinjau Kemiripan Gambar")
        self.window.geometry("1050x800")
        self.window.minsize(850, 700)
        self.window.transient(parent)
        self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.tutup)

        self.status = tk.StringVar(
            value="Siap memeriksa kemiripan gambar."
        )
        self.ambang = tk.StringVar(value="5")
        self.info = tk.StringVar(value="Belum ada hasil.")
        self.keputusan_var = tk.StringVar(
            value="Keputusan: belum ada pasangan."
        )

        self.panel_gambar = []
        self.nama_gambar = []
        self.tombol_keputusan = []

        self.buat_tampilan()
        self.window.after(100, self.periksa_antrean)

        if self.gagal_memuat:
            self.status.set(
                "Laporan lama gagal dibaca. "
                "Pencarian tetap tersedia, tetapi penyimpanan diblokir."
            )

    def muat_keputusan(self):
        if not self.file_keputusan.exists():
            return

        try:
            isi = json.loads(
                self.file_keputusan.read_text(encoding="utf-8")
            )

            if not isinstance(isi, dict):
                raise ValueError("Isi laporan harus berupa objek JSON.")

            keputusan = isi.get("keputusan")

            if not isinstance(keputusan, dict):
                raise ValueError("Bagian keputusan tidak valid.")

            for catatan in keputusan.values():
                if not isinstance(catatan, dict):
                    raise ValueError("Ada catatan keputusan tidak valid.")

                if catatan.get("status") not in NAMA_STATUS:
                    raise ValueError("Ada status keputusan tidak dikenal.")

            self.keputusan = keputusan

        except Exception as error:
            self.gagal_memuat = str(error)

    def buat_tampilan(self):
        frame = ttk.Frame(self.window, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Pemeriksaan Kemiripan Visual",
            font=("", 17, "bold")
        ).pack(anchor=tk.W)

        ttk.Label(
            frame,
            text=f"Dataset: {self.folder}",
            wraplength=980
        ).pack(anchor=tk.W, pady=(5, 0))

        ttk.Label(
            frame,
            textvariable=self.status,
            wraplength=980
        ).pack(anchor=tk.W, pady=10)

        # Pengaturan pencarian.
        kontrol = ttk.Frame(frame)
        kontrol.pack(fill=tk.X)

        ttk.Label(
            kontrol,
            text="Ambang jarak dHash (0–64):"
        ).pack(side=tk.LEFT)

        self.input_ambang = ttk.Spinbox(
            kontrol,
            from_=0,
            to=64,
            textvariable=self.ambang,
            width=5
        )
        self.input_ambang.pack(side=tk.LEFT, padx=8)

        self.tombol_mulai = ttk.Button(
            kontrol,
            text="Cari Gambar Mirip",
            command=self.mulai
        )
        self.tombol_mulai.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(
            frame,
            mode="indeterminate"
        )
        self.progress.pack(fill=tk.X, pady=12)

        ttk.Label(
            frame,
            textvariable=self.info,
            wraplength=980
        ).pack(anchor=tk.W)

        # Dua gambar berdampingan.
        panel = ttk.Frame(frame)
        panel.pack(fill=tk.BOTH, expand=True, pady=12)

        panel.columnconfigure(0, weight=1, uniform="gambar")
        panel.columnconfigure(1, weight=1, uniform="gambar")
        panel.rowconfigure(0, weight=1)

        for posisi in range(2):
            bagian = ttk.Frame(panel)
            bagian.grid(
                row=0,
                column=posisi,
                sticky="nsew",
                padx=5
            )

            nama = tk.StringVar(value="")

            ttk.Label(
                bagian,
                textvariable=nama,
                wraplength=400
            ).pack(pady=(0, 8))

            label = ttk.Label(
                bagian,
                text="Belum ada gambar",
                anchor=tk.CENTER
            )
            label.pack(fill=tk.BOTH, expand=True)

            self.nama_gambar.append(nama)
            self.panel_gambar.append(label)

        # Keputusan pemeriksaan.
        ttk.Label(
            frame,
            textvariable=self.keputusan_var,
            wraplength=980
        ).pack(anchor=tk.W, pady=(0, 8))

        bar_keputusan = ttk.Frame(frame)
        bar_keputusan.pack(fill=tk.X, pady=(0, 10))

        pilihan = [
            ("Duplikat / daun yang sama", "terkait"),
            ("Gambar berbeda", "berbeda"),
            ("Perlu ditinjau", "tinjau")
        ]

        for teks, nilai in pilihan:
            tombol = ttk.Button(
                bar_keputusan,
                text=teks,
                command=lambda status=nilai: self.simpan_keputusan(
                    status
                ),
                state=tk.DISABLED
            )
            tombol.pack(side=tk.LEFT, padx=(0, 8))
            self.tombol_keputusan.append(tombol)

        # Navigasi.
        navigasi = ttk.Frame(frame)
        navigasi.pack(fill=tk.X)

        self.sebelumnya = ttk.Button(
            navigasi,
            text="← Sebelumnya",
            command=lambda: self.pindah(-1),
            state=tk.DISABLED
        )
        self.sebelumnya.pack(side=tk.LEFT)

        self.berikutnya = ttk.Button(
            navigasi,
            text="Berikutnya →",
            command=lambda: self.pindah(1),
            state=tk.DISABLED
        )
        self.berikutnya.pack(side=tk.LEFT, padx=8)

        ttk.Button(
            navigasi,
            text="Tutup / Hentikan",
            command=self.tutup
        ).pack(side=tk.RIGHT)

        ttk.Label(
            frame,
            text=(
                "Jarak kecil berarti pola hash lebih mirip, "
                "bukan persentase kemiripan. "
                "Semua kandidat perlu diperiksa secara visual. "
                "Tidak ada gambar yang dihapus."
            ),
            wraplength=980
        ).pack(anchor=tk.W, pady=10)

        ttk.Label(
            frame,
            text=f"Laporan keputusan: {self.file_keputusan}",
            wraplength=980
        ).pack(anchor=tk.W)

    def mulai(self):
        if self.sedang_memproses:
            return

        try:
            ambang = int(self.ambang.get())

            if not 0 <= ambang <= 64:
                raise ValueError

        except ValueError:
            messagebox.showwarning(
                "Ambang tidak valid",
                "Isi ambang dengan bilangan bulat antara 0 dan 64.",
                parent=self.window
            )
            return

        self.pasangan = []
        self.indeks = 0
        self.sedang_memproses = True

        self.keputusan_var.set(
            "Keputusan: menunggu hasil pencarian."
        )

        for tombol in self.tombol_keputusan:
            tombol.configure(state=tk.DISABLED)

        for label, nama in zip(
            self.panel_gambar,
            self.nama_gambar
        ):
            label.configure(
                image="",
                text="Menunggu hasil..."
            )
            label.image = None
            nama.set("")

        self.info.set("Sedang mencari kandidat...")
        self.status.set("Memindai file dataset...")

        self.sebelumnya.configure(state=tk.DISABLED)
        self.berikutnya.configure(state=tk.DISABLED)
        self.tombol_mulai.configure(state=tk.DISABLED)
        self.input_ambang.configure(state=tk.DISABLED)

        self.progress.start(10)

        Thread(
            target=self.proses,
            args=(ambang,),
            daemon=True
        ).start()

    def proses(self, ambang):
        """Pemrosesan latar belakang; tidak mengakses widget Tk."""
        try:
            if not self.folder.is_dir():
                raise ValueError("Folder dataset tidak ditemukan.")

            daftar = []

            for path in self.folder.rglob("*"):
                if self.berhenti.is_set():
                    return

                relatif = path.relative_to(self.folder)

                if len(relatif.parts) < 2:
                    continue

                if any(
                    bagian.startswith(".") or bagian == "__MACOSX"
                    for bagian in relatif.parts
                ):
                    continue

                if (
                    path.is_file()
                    and path.suffix.lower() in EKSTENSI
                ):
                    daftar.append(path)

            daftar.sort(key=lambda path: str(path).lower())

            hashes = []
            gagal = []

            for nomor, path in enumerate(daftar, start=1):
                if self.berhenti.is_set():
                    return

                try:
                    hashes.append((path, hitung_dhash(path)))

                except Exception as error:
                    gagal.append(
                        f"{path.relative_to(self.folder)}: {error}"
                    )

                if nomor % 20 == 0 or nomor == len(daftar):
                    self.antrean.put((
                        "status",
                        f"Membaca pola gambar "
                        f"{nomor}/{len(daftar)}..."
                    ))

            pasangan = []

            for i, (path_a, hash_a) in enumerate(hashes):
                if self.berhenti.is_set():
                    return

                for j in range(i + 1, len(hashes)):
                    if j % 250 == 0 and self.berhenti.is_set():
                        return

                    path_b, hash_b = hashes[j]
                    jarak = (hash_a ^ hash_b).bit_count()

                    if jarak <= ambang:
                        pasangan.append((
                            jarak,
                            path_a,
                            path_b
                        ))

                if i % 50 == 0:
                    self.antrean.put((
                        "status",
                        f"Membandingkan gambar "
                        f"{i + 1}/{len(hashes)}..."
                    ))

            pasangan.sort(key=lambda item: item[0])

            self.antrean.put((
                "selesai",
                (pasangan, gagal, len(hashes))
            ))

        except Exception as error:
            self.antrean.put(("error", str(error)))

    def periksa_antrean(self):
        if self.ditutup:
            return

        for _ in range(100):
            try:
                jenis, data = self.antrean.get_nowait()
            except Empty:
                break

            if jenis == "status":
                self.status.set(data)
                continue

            self.progress.stop()
            self.sedang_memproses = False
            self.tombol_mulai.configure(state=tk.NORMAL)
            self.input_ambang.configure(state=tk.NORMAL)

            if jenis == "error":
                self.status.set(
                    f"Pemeriksaan gagal: {data}"
                )
                self.info.set("Pencarian tidak selesai.")

            elif jenis == "selesai":
                self.pasangan, gagal, jumlah_dibaca = data

                self.status.set(
                    f"Selesai: {jumlah_dibaca} gambar diproses, "
                    f"{len(self.pasangan)} pasangan kandidat, "
                    f"{len(gagal)} file gagal."
                )

                if gagal:
                    for pesan in gagal:
                        print("[Kemiripan] Gagal:", pesan)

                    messagebox.showwarning(
                        "Ada file gagal diproses",
                        f"{len(gagal)} file gagal diproses.\n"
                        "Rincian tersedia di terminal.",
                        parent=self.window
                    )

                if self.pasangan:
                    self.tampilkan_pasangan()
                else:
                    self.info.set(
                        "Tidak ditemukan kandidat pada ambang ini. "
                        "Ini bukan jaminan tidak ada gambar mirip."
                    )

                    self.keputusan_var.set(
                        "Tidak ada pasangan untuk ditinjau."
                    )

                    for label in self.panel_gambar:
                        label.configure(
                            image="",
                            text="Tidak ada kandidat"
                        )

        self.window.after(100, self.periksa_antrean)

    def tampilkan_pasangan(self):
        if not self.pasangan:
            return

        jarak, path_a, path_b = self.pasangan[self.indeks]

        kategori_a = path_a.relative_to(self.folder).parts[0]
        kategori_b = path_b.relative_to(self.folder).parts[0]

        keterangan = (
            "LINTAS KATEGORI — periksa label"
            if kategori_a != kategori_b
            else "Kategori sama"
        )

        self.info.set(
            f"Pasangan {self.indeks + 1}/{len(self.pasangan)} | "
            f"Jarak dHash: {jarak}/64 | {keterangan}"
        )

        berhasil_tampil = True

        for posisi, path in enumerate((path_a, path_b)):
            label = self.panel_gambar[posisi]

            self.nama_gambar[posisi].set(
                str(path.relative_to(self.folder))
            )

            try:
                with Image.open(path) as sumber:
                    gambar = ImageOps.exif_transpose(
                        sumber
                    ).convert("RGB")

                    gambar.thumbnail(
                        (390, 330),
                        Image.Resampling.LANCZOS
                    )

                foto = ImageTk.PhotoImage(
                    gambar,
                    master=self.window
                )

                label.configure(image=foto, text="")
                label.image = foto

            except Exception as error:
                berhasil_tampil = False
                label.configure(
                    image="",
                    text=f"Gagal menampilkan:\n{error}"
                )
                label.image = None

        self.sebelumnya.configure(
            state=(
                tk.NORMAL
                if self.indeks > 0
                else tk.DISABLED
            )
        )

        self.berikutnya.configure(
            state=(
                tk.NORMAL
                if self.indeks < len(self.pasangan) - 1
                else tk.DISABLED
            )
        )

        boleh_menyimpan = (
            berhasil_tampil and not self.gagal_memuat
        )

        for tombol in self.tombol_keputusan:
            tombol.configure(
                state=(
                    tk.NORMAL
                    if boleh_menyimpan
                    else tk.DISABLED
                )
            )

        if self.gagal_memuat:
            self.keputusan_var.set(
                "Penyimpanan diblokir karena laporan lama gagal dibaca: "
                f"{self.gagal_memuat}"
            )
            return

        if not berhasil_tampil:
            self.keputusan_var.set(
                "Keputusan dinonaktifkan karena gambar gagal ditampilkan."
            )
            return

        try:
            kunci, _ = self.identitas_pasangan(path_a, path_b)
            catatan = self.keputusan.get(kunci)

            if catatan:
                status = NAMA_STATUS.get(
                    catatan.get("status"),
                    "Status tidak dikenal"
                )

                self.keputusan_var.set(
                    f"Keputusan tersimpan: {status}"
                )
            else:
                self.keputusan_var.set(
                    "Keputusan: belum diperiksa."
                )

        except OSError as error:
            for tombol in self.tombol_keputusan:
                tombol.configure(state=tk.DISABLED)

            self.keputusan_var.set(
                f"Tidak dapat membaca identitas file: {error}"
            )

    def identitas_pasangan(self, path_a, path_b):
        """
        Identitas berdasarkan lokasi, ukuran, dan waktu perubahan.
        Perubahan file menyebabkan keputusan lama tidak langsung dipakai.
        """
        identitas = []

        for path in sorted(
            (path_a, path_b),
            key=lambda item: str(item.resolve())
        ):
            info = path.stat()

            identitas.append({
                "path": str(path.resolve()),
                "ukuran_bytes": info.st_size,
                "mtime_ns": info.st_mtime_ns
            })

        teks = json.dumps(
            identitas,
            sort_keys=True,
            ensure_ascii=False
        )

        kunci = hashlib.sha256(
            teks.encode("utf-8")
        ).hexdigest()

        return kunci, identitas

    def simpan_keputusan(self, status):
        if not self.pasangan or self.sedang_memproses:
            return

        if status not in NAMA_STATUS:
            return

        if self.gagal_memuat:
            messagebox.showerror(
                "Laporan perlu diperiksa",
                "Laporan lama tidak dapat dibaca. "
                "Penyimpanan dihentikan agar tidak tertimpa.\n\n"
                f"{self.file_keputusan}\n\n"
                f"Alasan: {self.gagal_memuat}",
                parent=self.window
            )
            return

        jarak, path_a, path_b = self.pasangan[self.indeks]

        try:
            kunci, identitas = self.identitas_pasangan(
                path_a, path_b
            )

            keputusan_baru = dict(self.keputusan)

            keputusan_baru[kunci] = {
                "status": status,
                "jarak_dhash": jarak,
                "file": identitas,
                "waktu_utc": datetime.now(
                    timezone.utc
                ).isoformat()
            }

            laporan = {
                "versi": 1,
                "dataset": str(self.folder),
                "metode": "dHash 64 bit dan tinjauan manual",
                "keputusan": keputusan_baru
            }

            self.folder_laporan.mkdir(
                parents=True,
                exist_ok=True
            )

            sementara = self.file_keputusan.with_suffix(".tmp")

            sementara.write_text(
                json.dumps(
                    laporan,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            sementara.replace(self.file_keputusan)
            self.keputusan = keputusan_baru

            self.keputusan_var.set(
                f"Tersimpan: {NAMA_STATUS[status]}"
            )

        except Exception as error:
            messagebox.showerror(
                "Gagal menyimpan keputusan",
                str(error),
                parent=self.window
            )

    def pindah(self, arah):
        tujuan = self.indeks + arah

        if 0 <= tujuan < len(self.pasangan):
            self.indeks = tujuan
            self.tampilkan_pasangan()

    def tutup(self):
        self.ditutup = True
        self.berhenti.set()
        self.window.destroy()