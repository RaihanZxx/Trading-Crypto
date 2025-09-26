# Crypto Trading Screener - Ringkasan Dokumentasi

## Gambaran Umum
Crypto Trading Screener adalah alat otomatisasi untuk memantau pasar futures kripto dan mengidentifikasi aset terbaik dan terburuk berdasarkan perubahan harga dari harga pembukaan harian. Sistem ini mengambil data dari bursa Bitget, menyimpannya di database lokal, dan mengirimkan notifikasi via Telegram.

Proyek ini juga mencakup mesin OFI (Order Flow Imbalance) yang dibangun dengan Rust untuk analisis performa tinggi terhadap data pasar secara real-time dari koneksi WebSocket.

## Instalasi
1. Clone repositori:
   ```bash
   git clone https://github.com/RaihanZxx/Trading-Crypto
   cd Trading-Crypto
   ```

2. Pastikan Rust terinstal:
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source ~/.cargo/env
   ```

3. Buat virtual environment dan instal dependensi:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   cd src && cargo build --release
   ```

## Konfigurasi
Setelah menginstal, salin file konfigurasi dan atur kredensial Anda:
```bash
cp .env.example .env
```

## Penggunaan
Jalankan screener dengan:
```bash
python src/main.py
```

## Fitur Utama

### Screener
- Mengambil harga pembukaan untuk semua simbol futures pada 00:00 UTC
- Menghitung perubahan harga sepanjang hari
- Mengidentifikasi 10 besar pemenang dan pecundang
- Mengirimkan hasil via Telegram

### OFI Sentinel (Rust Daemon)
- Aplikasi daemon berbasis Rust yang berjalan terus menerus (24/7)
- Mengelola tugas analisis konkuren secara bersamaan
- Menghubungkan ke layanan Python untuk screening dan eksekusi perdagangan
- Menyaring simbol-simbol yang layak dimonitor secara berkala

### Risk Management System
- Manajemen risiko 1% per perdagangan
- Perhitungan ukuran posisi dinamis berdasarkan ekuitas akun
- Stop-loss otomatis di 1% dari harga masuk
- Batas maksimum posisi konkuren
- Pelacakan posisi secara real-time
- Mode uji coba (paper trading) untuk pengujian tanpa modal asli

## Konfigurasi Utama (config.toml)

### Bagian [execution]
```toml
[execution]
max_concurrent_positions = 5      # Maksimum posisi terbuka sekaligus
stop_loss_percent = 0.01          # Stop loss 1% dari harga masuk
risk_percentage = 0.01            # Risiko 1% dari ekuitas per perdagangan
use_dynamic_risk = true           # Gunakan perhitungan risiko dinamis
```

## Komponen Utama

### Screener
- `screener.py`: Logika inti untuk mengambil harga, menghitung perubahan, dan mengidentifikasi pemenang/pecundang

### Execution Service
- `execution_service/manager.py`: Layanan Python untuk eksekusi perdagangan dan manajemen risiko lanjutan

### OFI Engine (Rust)
- Mesin analisis performa tinggi untuk mendeteksi peluang perdagangan
- Terhubung ke WebSocket bursa untuk data real-time
- Mendeteksi sinyal berdasarkan imbalance dan dinamika order book

## Database
- Menggunakan SQLite untuk menyimpan data harga pembukaan dan hasil screening
- Skema: tabel `open_prices` dengan kolom symbol, open_price, timestamp

## API Utama
- `exchange_service.py`: Fungsionalitas untuk berinteraksi dengan API Bitget
- `database.py`: Fungsionalitas untuk manajemen database
- `screener.py`: Fungsionalitas screening utama
- `execution_service/manager.py`: Fungsionalitas eksekusi perdagangan