<div align="center">
<h1 align="center">Trading-Crypto Project</h1>
<p align="center">
Bot trading cryptocurrency berkinerja tinggi yang dibuat dengan Python dan Rust untuk otomatisasi, analisis kuantitatif, dan eksekusi algoritma di bursa berjangka.
</p>
</div>
<div align="center">
<!-- Shields.io Badges -->
<a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg?style=for-the-badge&logo=python" alt="Python Version"></a>
<a href="https://www.rust-lang.org/"><img src="https://img.shields.io/badge/rust-1.70+-orange.svg?style=for-the-badge&logo=rust" alt="Rust Version"></a>
<a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge" alt="License: MIT"></a>
<a href="#"><img src="https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge" alt="Code Style: Black"></a>
<br>
<a href="#"><img src="https://img.shields.io/badge/status-aktif-brightgreen?style=for-the-badge" alt="Project Status"></a>
<a href="#"><img src="https://img.shields.io/badge/Made%20with-Love-red?style=for-the-badge&logo=heart" alt="Made with Love"></a>
</div>

---

## ✨ Fitur Utama

- **`screener`**: Memindai semua mata uang kripto untuk menemukan peluang di antara koin-koin Top 10 Gainer & Loser.
- **`OFI Sentinel`**: Aplikasi daemon berbasis Rust yang berjalan terus-menerus (24/7) sebagai otak utama dari operasi. Sentinel ini mengelola beberapa *task* analisis secara konkuren, memanggil Python Screener secara periodik untuk mendapatkan daftar koin pantauan terbaru, dan memanggil Python Execution Service saat sinyal perdagangan terdeteksi. Setiap *task* analisis memiliki koneksi WebSocket sendiri untuk menerima data real-time dan mendeteksi sinyal berdasarkan algoritma OFI.
- **`Risk Management`**: Sistem manajemen risiko canggih dengan fitur 1% risiko per perdagangan (dynamic risk) yang otomatis menghitung ukuran posisi berdasarkan equity akun, serta stop-loss otomatis untuk melindungi modal.
- **`WebSocket Connectors`**: Koneksi real-time ke exchange untuk data order book dan trade terbaru.
- **`Multi-language`**: Kombinasi Python untuk logika tingkat tinggi dan Rust untuk komputasi performa tinggi.

---

## 🚀 Memulai

### Prasyarat

- Python 3.11+
- Rust 1.70+ 
- Virtual environment (direkomendasikan)

### Instalasi

1. **Pastikan Rust terinstal:**
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source ~/.cargo/env
   ```

2. **Buat lingkungan virtual:**
   ```bash
   python3 -m venv .venv
   ```

3. **Aktifkan lingkungan virtual:**
   ```bash
   source .venv/bin/activate  # Di Windows: .venv\Scripts\activate
   ```

4. **Instal paket yang diperlukan:**
   ```bash
   pip install -e .
   ```

5. **Bangun modul Rust (jika tersedia):**
   ```bash
   cd src && maturin develop --release
   ```

---

## 💡 Penggunaan

Jalankan berbagai modul dengan perintah sederhana:

- **Jalankan Screener:**
  ```bash
  crypto screener
  ```

- **Jalankan analisis OFI:**
  ```bash
  # Menggunakan wrapper Python untuk mesin Rust
  python -c "from src.strategy.OFI.wrapper import analyze_symbol; signal = analyze_symbol('BTCUSDT'); print(signal)"
  ```

- **Jalankan OFI Sentinel (daemon utama):**
  ```bash
  cd src && cargo run
  ```

## 🛡️ Manajemen Risiko

Sistem ini dilengkapi dengan fitur manajemen risiko canggih:

- **1% Risiko Per Perdagangan**: Ukuran posisi dihitung secara dinamis berdasarkan 1% dari equity akun
- **Stop-Loss Otomatis**: Setiap perdagangan dilengkapi dengan stop-loss 1% dari harga entry
- **Manajemen Posisi**: Sistem melacak semua posisi aktif dan memonitor statusnya secara real-time
- **Batas Posisi Maksimum**: Konfigurasi untuk membatasi jumlah posisi yang dapat dibuka secara bersamaan
- **Monitoring Otomatis**: Setiap posisi dipantau terus-menerus hingga ditutup

### Konfigurasi Risiko di config.toml

```toml
[execution]
# Manajemen risiko
max_concurrent_positions = 5
stop_loss_percent = 0.01  # 1% stop loss
risk_percentage = 0.01    # 1% risiko per perdagangan dari total balance
use_dynamic_risk = true   # Menggunakan equity akun secara dinamis
```

---

## 📚 Dokumentasi

Dokumentasi lengkap tersedia di direktori [doc/](doc/):

- [DOCUMENTATION.md](doc/DOCUMENTATION.md) - Dokumentasi utama proyek
- [CHANGELOG.md](doc/CHANGELOG.md) - Riwayat perubahan proyek
- [CONTRIBUTING.md](doc/CONTRIBUTING.md) - Panduan kontribusi
- [CODE_OF_CONDUCT.md](doc/CODE_OF_CONDUCT.md) - Kode etik kontributor

---

## 🏛️ Arsitektur Proyek

Proyek ini terorganisir ke dalam komponen-komponen modular untuk kemudahan pengembangan dan pemeliharaan.

```
/
├── config/                 # File konfigurasi
├── data/                   # File database SQLite
├── doc/                    # Dokumentasi proyek
└── src/
    ├── Cargo.toml          # Konfigurasi build Rust
    ├── main.rs             # OFI Sentinel - aplikasi daemon utama berbasis Rust
    ├── connectors/         # Konektor API Bursa (Python & Rust)
    │   ├── exchange_service.py
    │   └── websocket.rs
    ├── database/           # Operasi database
    ├── execution_service/  # Service eksekusi perdagangan berbasis Python
    │   ├── __init__.py
    │   └── manager.py
    ├── screener/           # Logika aplikasi Screener
    │   ├── __init__.py
    │   └── screener.py
    ├── strategy/           # Implementasi strategi perdagangan
    │   └── OFI/            # Order Flow Imbalance analysis
    │       ├── data.rs     # Struktur data untuk order book dan trade
    │       ├── engine.rs   # Mesin analisis OFI
    │       ├── ofi.rs      # Algoritma OFI
    │       ├── signals.rs  # Deteksi sinyal perdagangan
    │       └── websocket.rs # Koneksi WebSocket untuk data real-time
    ├── test/               # File test
    ├── utils/              # Fungsi utilitas (Python & Rust)
    │   └── lib.rs          # Definisi modul Rust
    └── main.py             # Titik masuk aplikasi Python (lama)
```

- `src/main.rs`: OFI Sentinel - aplikasi daemon utama berbasis Rust yang mengelola analisis konkuren
- `src/connectors/`: Konektor API exchange (Python & Rust)
- `src/database/`: Operasi database
- `src/execution_service/`: Service Python untuk eksekusi perdagangan dan manajemen risiko
- `src/screener/`: Modul Screener untuk analisis pasar (sekarang berfungsi sebagai service layer)
- `src/strategy/OFI/`: Implementasi lengkap strategi OFI (data, engine, algoritma, sinyal, WebSocket)
- `src/test/`: File test
- `src/utils/`: Fungsi utilitas dan definisi modul Rust
- `data/`: File database SQLite (crypto_screener.db dan telegram_state.json)
- `doc/`: Dokumentasi proyek
- `config/`: File konfigurasi untuk parameter strategi

Setiap modul di `src/` adalah paket Python dengan file `__init__.py` sendiri.