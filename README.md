<div align="center">
<h1 align="center">Trading-Crypto Project</h1>
<p align="center">
Bot trading cryptocurrency berkinerja tinggi yang dibuat dengan Python untuk otomatisasi, analisis kuantitatif, dan eksekusi algoritma di bursa berjangka.
</p>
</div>
<div align="center">
<!-- Shields.io Badges -->
<a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg?style=for-the-badge&logo=python" alt="Python Version"></a>
<a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge" alt="License: MIT"></a>
<a href="#"><img src="https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge" alt="Code Style: Black"></a>
<br>
<a href="#"><img src="https://img.shields.io/badge/status-aktif-brightgreen?style=for-the-badge" alt="Project Status"></a>
<a href="#"><img src="https://img.shields.io/badge/Made%20with-Love-red?style=for-the-badge&logo=heart" alt="Made with Love"></a>
</div>

---

## ✨ Fitur Utama

- **`screener`**: Memindai semua mata uang kripto untuk menemukan peluang di antara koin-koin Top 10 Gainer & Loser.

---

## 🚀 Memulai

### Prasyarat

- Python 3.11+
- Virtual environment (direkomendasikan)

### Instalasi

1. **Buat lingkungan virtual:**
   ```bash
   python3 -m venv .venv
   ```

2. **Aktifkan lingkungan virtual:**
   ```bash
   source .venv/bin/activate
   ```

3. **Instal paket yang diperlukan:**
   ```bash
   pip install -e .
   ```

---

## 💡 Penggunaan

Jalankan berbagai modul dengan perintah sederhana:

- **Jalankan Screener:**
  ```bash
  crypto screener
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
├── data/                   # File database SQLite
├── doc/                    # Dokumentasi proyek
└── src/
    ├── connectors/         # Konektor API Bursa
    ├── database/           # Operasi database
    ├── screener/           # Logika aplikasi Screener
    ├── test/               # File test
    ├── utils/              # Fungsi utilitas
    └── main.py             # Titik masuk aplikasi
```

- `src/connectors/`: Exchange API connectors
- `src/database/`: Database operations
- `src/screener/`: Screener Module
- `src/test/`: Test files
- `src/utils/`: Utility functions
- `data/`: SQLite database file (stores crypto_screener.db and telegram_state.json)
- `doc/`: Project documentation

Each module in `src/` is a Python package with its own `__init__.py` file.