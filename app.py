import io
import os
from urllib.parse import urlencode

from bs4 import BeautifulSoup
import pandas as pd
import requests
import streamlit as st

# --- KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="ETLE Auto-Save Checker (20k Nopol)",
    page_icon="⚡",
    layout="wide",
)

FULL_HEADERS = [
    "No. Baris",
    "Plat Nomor",
    "No Rangka",
    "No Mesin",
    "Status ETLE",
    "Link Pengecekan",
    "Lokasi",
    "Tanggal",
    "Jenis Pelanggaran",
    "Status",
    "Link Detail",
    "Path Foto",
    "Detail Jenis Pelanggaran",
    "Dasar Hukum",
    "Waktu Kejadian",
    "Merk",
    "Tipe",
    "Warna",
    "Nomor Rangka Detail",
    "Model",
    "Tahun",
    "Nomor Mesin Detail",
    "STNK Berlaku Sampai",
    "Estimasi Denda",
]

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
CHECKPOINT_FILE = "checkpoint_hasil_etle.csv"


# --- FUNGSI HITUNG DENDA ---
def hitung_denda(jenis_pelanggaran):
  text = str(jenis_pelanggaran).lower()
  if any(x in text for x in ["handphone", "ponsel", "wajar"]):
    return 750000
  elif "helm" in text:
    return 250000
  elif any(x in text for x in ["sabuk", "safety belt"]):
    return 250000
  elif any(x in text for x in ["dua orang", "berboncengan"]):
    return 250000
  elif any(
      x in text
      for x in [
          "rambu",
          "marka",
          "lampu",
          "arus",
          "jalur",
          "ganjil",
          "genap",
          "kecepatan",
          "stnk",
          "keabsahan",
      ]
  ):
    return 500000
  else:
    return 0


# --- SCRAPE DETAIL VIA HTTP REQUEST ---
def scrape_violation_details(session, detail_url):
  detailed_data = {}
  try:
    r = session.get(detail_url, headers=HTTP_HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    container = soup.select_one("div.col-10.d-flex.flex-column")

    if container:
      img_element = container.find("img")
      if img_element and img_element.get("src"):
        img_src = img_element["src"]
        detailed_data["Path Foto"] = (
            "https://etle-pmj.id" + img_src
            if img_src.startswith("/")
            else img_src
        )
      else:
        detailed_data["Path Foto"] = "-"

      full_text = container.get_text()

      def extract_info(text, keyword):
        try:
          return text.split(keyword)[1].split("\n")[1].strip()
        except (IndexError, ValueError):
          return "-"

      detailed_data["Detail Jenis Pelanggaran"] = extract_info(
          full_text, "Data Pelanggaran"
      )
      detailed_data["Dasar Hukum"] = extract_info(
          full_text, detailed_data.get("Detail Jenis Pelanggaran", "")
      )
      detailed_data["Waktu Kejadian"] = extract_info(
          full_text, "Hari, Tanggal & Waktu"
      )
      detailed_data["Merk"] = extract_info(full_text, "Merk")
      detailed_data["Tipe"] = extract_info(full_text, "Tipe")
      detailed_data["Warna"] = extract_info(full_text, "Warna")
      detailed_data["Nomor Rangka Detail"] = extract_info(
          full_text, "Nomor Rangka"
      )
      detailed_data["Model"] = extract_info(full_text, "Model")
      detailed_data["Tahun"] = extract_info(full_text, "Tahun")
      detailed_data["Nomor Mesin Detail"] = extract_info(
          full_text, "Nomor Mesin"
      )
      detailed_data["STNK Berlaku Sampai"] = extract_info(
          full_text, "STNK Berlaku Sampai"
      )
  except Exception:
    pass
  return detailed_data


# --- CEK STATUS ETLE VIA HTTP REQUEST ---
def check_etle_status(session, url):
  try:
    r = session.get(url, headers=HTTP_HEADERS, timeout=20)
    soup = BeautifulSoup(r.text, "html.parser")

    popup = soup.select_one("div.swal2-html-container")
    if popup and "tidak ditemukan" in popup.text.lower():
      return "Aman", None

    rows = soup.select("tbody tr")
    violations = []
    for row in rows:
      cols = row.find_all("td")
      detail_link = ""
      link_element = row.select_one("a.btn-secondary")
      if link_element and link_element.get("href"):
        href = link_element["href"]
        detail_link = (
            href
            if href.startswith("http")
            else "https://etle-pmj.id" + (href if href.startswith("/") else "/" + href)
        )

      if len(cols) >= 4:
        violations.append({
            "Tanggal": cols[0].get_text(strip=True),
            "Lokasi": cols[1].get_text(strip=True),
            "Jenis Pelanggaran": cols[2].get_text(strip=True),
            "Status": cols[3].get_text(strip=True),
            "Link Detail": detail_link,
        })

    return ("Ada ETLE", violations) if violations else ("Aman", None)
  except Exception as e:
    return f"Error: {e}", None


# --- AUTO-SAVE: DITULIS LANGSUNG KE HARDDISK PER BARIS ---
def append_to_checkpoint(row_data_list):
  df_new = pd.DataFrame(row_data_list).reindex(columns=FULL_HEADERS)
  file_exists = os.path.isfile(CHECKPOINT_FILE)
  df_new.to_csv(
      CHECKPOINT_FILE,
      mode="a",
      index=False,
      header=not file_exists,
      encoding="utf-8-sig",
  )


# --- ANTARMUKA STREAMLIT ---
st.title("⚡ ETLE Automated Checker (Skala Besar 20k Nopol)")
st.write(
    "Menggunakan **HTTP Requests (Cepat)** + **Auto-Save & Resume**."
    " Hasil langsung tersimpan ke harddisk per nopol."
)

# Tampilkan status checkpoint jika file lokal sudah ada
if os.path.exists(CHECKPOINT_FILE):
  try:
    df_cp = pd.read_csv(CHECKPOINT_FILE, dtype=str)
    st.warning(
        f"📂 Checkpoint Ditemukan! **{len(df_cp)} data** tersimpan secara aman."
    )

    col1, col2 = st.columns(2)
    with col1:
      output_stream = io.BytesIO()
      with pd.ExcelWriter(output_stream, engine="openpyxl") as writer:
        df_cp.to_excel(writer, index=False)
      st.download_button(
          "📥 Download Data Tersimpan (.xlsx)",
          data=output_stream.getvalue(),
          file_name="HASIL_PROSES_TERSIMPAN.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      )
    with col2:
      if st.button("🗑️ Hapus Checkpoint & Reset"):
        os.remove(CHECKPOINT_FILE)
        st.rerun()
  except Exception:
    pass

uploaded_file = st.file_uploader(
    "Upload File Excel Input", type=["xlsx", "xls"]
)

if uploaded_file is not None:
  df = pd.read_excel(uploaded_file, dtype=str)

  col_plat = next((c for c in df.columns if "plat" in c.lower()), None)
  col_rangka = next((c for c in df.columns if "rangka" in c.lower()), None)
  col_mesin = next((c for c in df.columns if "mesin" in c.lower()), None)

  if not col_plat or not col_rangka or not col_mesin:
    st.error(
        "❌ Kolom Plat, No Rangka, atau No Mesin tidak ditemukan pada Excel!"
    )
  else:
    # Ambil plat yang sudah pernah diproses agar tidak ter-cek ulang saat resume
    processed_plats = set()
    if os.path.exists(CHECKPOINT_FILE):
      try:
        df_cp = pd.read_csv(CHECKPOINT_FILE, dtype=str)
        if "Plat Nomor" in df_cp.columns:
          processed_plats = set(df_cp["Plat Nomor"].dropna().str.strip())
      except Exception:
        pass

    total_data = len(df)
    sudah_proses = len(processed_plats)
    sisa_data = total_data - sudah_proses

    st.info(
        f"📊 **Total Data:** {total_data} | **Sudah Diproses:** {sudah_proses} |"
        f" **Sisa:** {sisa_data}"
    )

    if st.button("🚀 Mulai / Lanjutkan Pengecekan", type="primary"):
      progress_bar = st.progress(0)
      status_text = st.empty()
      log_box = st.expander("📄 Live Log Pengecekan", expanded=True)

      session = requests.Session()

      for idx, row in df.iterrows():
        plat = str(row[col_plat]).strip()
        rangka = str(row[col_rangka]).strip()
        mesin = str(row[col_mesin]).strip()
        real_row = idx + 2

        if not plat or plat.lower() == "nan":
          continue

        # LOGIKA RESUME: Lewati Nopol yang sudah ada di file checkpoint
        if plat in processed_plats:
          progress_bar.progress((idx + 1) / total_data)
          continue

        status_text.text(f"Memproses [{idx+1}/{total_data}]: {plat}")
        log_box.write(f"**[{idx+1}/{total_data}]** Memeriksa: `{plat}`")

        clean_plat = plat.replace(" ", "").replace("-", "")
        params = {
            "aksi": "cek",
            "nopol": clean_plat,
            "norangka": rangka,
            "nomesin": mesin,
        }
        url = "https://etle-pmj.id/?" + urlencode(params)

        status, violations = check_etle_status(session, url)

        base_row = dict.fromkeys(FULL_HEADERS, "-")
        base_row.update({
            "No. Baris": real_row,
            "Plat Nomor": plat,
            "No Rangka": rangka,
            "No Mesin": mesin,
            "Status ETLE": status,
            "Link Pengecekan": url,
        })

        rows_to_save = []
        if status == "Ada ETLE" and violations:
          log_box.warning(
              f"⚠️ **{plat}**: Ditemukan {len(violations)} pelanggaran!"
          )
          for v in violations:
            row_data = base_row.copy()
            row_data.update(v)
            if v.get("Link Detail"):
              det = scrape_violation_details(session, v["Link Detail"])
              row_data.update(det)
            if "Jenis Pelanggaran" in row_data:
              row_data["Estimasi Denda"] = hitung_denda(
                  row_data["Jenis Pelanggaran"]
              )
            rows_to_save.append(row_data)
        else:
          log_box.info(f"✅ **{plat}**: Status `{status}`")
          rows_to_save.append(base_row)

        # SIMPAN HASIL LANGSUNG KE DISK (AUTO-SAVE)
        append_to_checkpoint(rows_to_save)
        processed_plats.add(plat)
        progress_bar.progress((idx + 1) / total_data)

      st.success("🎉 Pengecekan 20k data selesai!")
      st.rerun()
