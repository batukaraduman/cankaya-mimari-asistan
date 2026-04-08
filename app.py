import streamlit as st
from supabase import create_client, Client
import time
import pandas as pd
from datetime import datetime, timedelta
import requests
import json
import re

# -----------------------------------------------------------------------------
# 1. AYARLAR VE KURULUM
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="YZ Mimari Asistan", 
    layout="wide",
    initial_sidebar_state="expanded"
)

try:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Supabase bağlantı hatası! .streamlit/secrets.toml dosyasını kontrol et.")
    st.stop()

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user' not in st.session_state:
    st.session_state.user = None
if 'role' not in st.session_state:
    st.session_state.role = 'student'

# --- SADECE REKLAM GİZLEYİCİ ---
hide_streamlit_style = """
            <style>
            footer {visibility: hidden;}
            [data-testid="stFooter"] {display: none !important;}
            .viewerBadge_container {display: none !important;}
            .viewerBadge_link {display: none !important;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. YARDIMCI FONKSİYONLAR
# -----------------------------------------------------------------------------
def clean_and_parse_json(raw_data):
    if not raw_data: return None
    if isinstance(raw_data, dict): return raw_data
    if isinstance(raw_data, str):
        match = re.search(r'\{.*\}', raw_data, re.DOTALL)
        if match:
            cleaned_text = match.group(0)
            try:
                return json.loads(cleaned_text)
            except Exception as e:
                pass
        temiz_ham_metin = raw_data.replace('```json', '').replace('```', '').strip()
        return {
            "puan": "-",
            "yorum": temiz_ham_metin,
            "oneri": "⚠️ (Yapay Zeka formatlama hatası yaptı ancak analiz metni yukarıdadır.)"
        }
    return None

def convert_to_trt(utc_time_str):
    try:
        dt_utc = datetime.strptime(utc_time_str[:19], "%Y-%m-%dT%H:%M:%S")
        dt_trt = dt_utc + timedelta(hours=3)
        return f"{dt_trt.strftime('%Y-%m-%d')} | Saat: {dt_trt.strftime('%H:%M')}"
    except:
        return utc_time_str

def login_user(email, password):
    try:
        response = supabase.auth.sign_in_with_password({"email": email, "password": password})
        st.session_state.logged_in = True
        st.session_state.user = response.user
        
        st.session_state.access_token = response.session.access_token
        st.session_state.refresh_token = response.session.refresh_token
        
        user_id = response.user.id
        role_data = supabase.table("user_roles").select("role").eq("user_id", user_id).execute()
        
        if role_data.data:
            st.session_state.role = role_data.data[0]['role']
        else:
            st.session_state.role = 'student'

        st.success(f"Giriş başarılı! Rol: {st.session_state.role}")
        time.sleep(1)
        st.rerun()
    except Exception as e:
        st.error("Giriş hatası: Lütfen e-posta ve şifrenizi kontrol edin.")

def logout_user():
    supabase.auth.sign_out()
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = 'student'
    st.rerun()

# -----------------------------------------------------------------------------
# 3. ANA UYGULAMA
# -----------------------------------------------------------------------------
def main_app():
    with st.sidebar:
        st.write(f"Kullanıcı: **{st.session_state.user.email}**")
        view_mode = "Öğrenci Görünümü"
        
        if st.session_state.role == 'admin':
            st.success("🎓 EĞİTMEN (ADMIN)")
            view_mode = st.radio("Görünüm Modu:", ["Yönetici Paneli", "Öğrenci Görünümü (Test)"])
        else:
            st.info("🎓 ÖĞRENCİ")
        
        st.divider()
        
        with st.expander("🔐 Şifre Değiştir"):
            yeni_sifre = st.text_input("Yeni Şifre", type="password")
            yeni_sifre_tekrar = st.text_input("Yeni Şifre (Tekrar)", type="password")
            
            if st.button("Şifreyi Güncelle", use_container_width=True):
                if len(yeni_sifre) < 6:
                    st.warning("Şifre en az 6 karakter olmalıdır.")
                elif yeni_sifre != yeni_sifre_tekrar:
                    st.error("Girdiğiniz şifreler eşleşmiyor!")
                else:
                    try:
                        supabase.auth.set_session(st.session_state.access_token, st.session_state.refresh_token)
                        supabase.auth.update_user({"password": yeni_sifre})
                        st.success("Şifreniz başarıyla güncellendi!")
                    except Exception as e:
                        st.error(f"Hata: Şifre güncellenemedi. ({e})")
        
        st.divider()
        
        if st.button("Çıkış Yap"):
            logout_user()

    # --- EKRAN 1: YÖNETİCİ PANELİ ---
    if st.session_state.role == 'admin' and view_mode == "Yönetici Paneli":
        st.title("👨‍🏫 Eğitmen Kontrol Paneli")
        try:
            response = supabase.table("projects").select("*").order('created_at', desc=True).execute()
            data = response.data
            
            if not data:
                st.info("Henüz yüklenen proje yok.")
            else:
                table_rows = []
                for p in data:
                    ai_data = clean_and_parse_json(p['ai_response'])
                    score = ai_data.get('puan', '-') if ai_data else '-'
                    status = "✅ Tamamlandı" if ai_data else "⏳ Bekliyor"
                    tarih_saat = convert_to_trt(p['created_at'])
                    
                    table_rows.append({
                        "ID": p['id'], 
                        "Tarih": tarih_saat,
                        "Öğrenci": p['user_email'],
                        "Puan": score,
                        "Durum": status,
                        "Resim": p['image_url'],
                        "Detay": ai_data
                    })
                
                df = pd.DataFrame(table_rows)

                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption("📋 Tüm Projelerin Listesi")
                    st.dataframe(df[["Tarih", "Öğrenci", "Puan", "Durum"]], use_container_width=True, hide_index=True, height=200)
                
                with col2:
                    st.metric("Toplam Proje", len(df))
                    st.metric("Tamamlanan", len(df[df["Durum"]=="✅ Tamamlandı"]))

                st.divider()
                st.subheader("🔍 Proje Detay İnceleme")
                
                options = {f"{row['Tarih']} | {row['Öğrenci']} | Puan: {row['Puan']}": row['ID'] for index, row in df.iterrows()}
                selected_option = st.selectbox("İncelemek istediğiniz projeyi listeden seçiniz:", ["Seçiniz..."] + list(options.keys()))

                if selected_option != "Seçiniz...":
                    selected_id = options[selected_option]
                    sel_row = df[df['ID'] == selected_id].iloc[0]
                    
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.image(sel_row['Resim'], caption="Öğrenci Çizimi", use_container_width=True)
                    with c2:
                        st.markdown("### 📝 Yapay Zeka Raporu")
                        if sel_row['Detay']:
                            st.write(f"**🏆 Puan:** {sel_row['Puan']}")
                            with st.container(border=True):
                                st.markdown("**Yorum:**")
                                st.write(sel_row['Detay'].get('yorum', '-'))
                            with st.container(border=True):
                                st.markdown("**Öneri:**")
                                st.write(sel_row['Detay'].get('oneri', '-'))
                        else:
                            st.warning("Bu proje henüz analiz edilmemiş.")

        except Exception as e:
            st.error(f"Veri hatası: {e}")

    # --- EKRAN 2: ÖĞRENCİ GÖRÜNÜMÜ ---
    else:
        st.title("🏛️ Proje Yükleme Alanı")
        tab1, tab2 = st.tabs(["📤 Proje Yükle", "🗂️ Geçmiş Projelerim"])
        
        with tab1:
            st.subheader("Yeni Proje Analizi")
            uploaded_file = st.file_uploader("Mimari Çizim Yükle", type=['png', 'jpg', 'jpeg'])
            
            if uploaded_file:
                col_left, col_right = st.columns([1, 1.5])
                
                with col_left:
                    st.image(uploaded_file, caption="Yüklenecek Çizim", use_container_width=True)
                    submit_button = st.button("📤 Analize Gönder", use_container_width=True)

                with col_right:
                    if submit_button:
                        with st.spinner("1/2: Çiziminiz sisteme yükleniyor..."):
                            try:
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                guvenli_isim = re.sub(r'[^a-zA-Z0-9_.-]', '', uploaded_file.name.replace(' ', '_'))
                                file_name = f"{timestamp}_{guvenli_isim}"
                                
                                file_bytes = uploaded_file.getvalue()
                                supabase.storage.from_("project-files").upload(path=file_name, file=file_bytes, file_options={"content-type": uploaded_file.type})
                                public_url = supabase.storage.from_("project-files").get_public_url(file_name)
                                
                                project_data = {"user_id": st.session_state.user.id, "user_email": st.session_state.user.email, "status": "pending", "image_url": public_url, "ai_response": {}}
                                response = supabase.table("projects").insert(project_data).execute()
                                new_record_id = response.data[0]['id']
                                
                                # --- YENİ SUNUCU WEBHOOK ADRESİN BURADA ---
                                n8n_url = "http://167.71.43.247:5678/webhook/mimari-analiz" 
                                requests.post(n8n_url, json={"record_id": new_record_id})
                                upload_success = True
                                
                            except Exception as e:
                                st.error(f"Yükleme Hatası: {e}")
                                upload_success = False

                        if upload_success:
                            with st.spinner("2/2: Uzman YZ çiziminizi inceliyor. Lütfen bekleyin..."):
                                max_attempts = 25  
                                ai_data = None
                                
                                for attempt in range(max_attempts):
                                    time.sleep(3)
                                    res = supabase.table("projects").select("ai_response").eq("id", new_record_id).execute()
                                    if res.data and res.data[0]['ai_response']:
                                        ai_data = clean_and_parse_json(res.data[0]['ai_response'])
                                        if ai_data: break
                                
                                if ai_data:
                                    st.success("🎉 Analiz Tamamlandı!")
                                    st.markdown("### 🤖 Yapay Zeka Kritiği")
                                    
                                    yorum_veri = ai_data.get('yorum', '-')
                                    oneri_veri = ai_data.get('oneri', '-')
                                    
                                    yorum_metni = "\n\n".join(yorum_veri) if isinstance(yorum_veri, list) else str(yorum_veri)
                                    oneri_metni = "\n\n".join(oneri_veri) if isinstance(oneri_veri, list) else str(oneri_veri)
                                    
                                    st.info(f"**📝 Yorum:**\n\n{yorum_metni}")
                                    st.warning(f"**💡 Öneri:**\n\n{oneri_metni}")
                                else:
                                    st.warning("⏳ Analiz süresi aşıldı. Sonuç arka planda hazırlanmaya devam ediyor. Geçmiş projelerden bakabilirsiniz.")

        with tab2:
            st.subheader("🗂️ Geçmiş Projelerim")
            try:
                user_id = st.session_state.user.id
                response = supabase.table("projects").select("*").eq("user_id", user_id).order('created_at', desc=True).execute()
                
                if not response.data:
                    st.info("Henüz proje yok.")
                else:
                    for p in response.data:
                        tarih_saat = convert_to_trt(p['created_at'])
                        ai_data = clean_and_parse_json(p['ai_response'])
                        durum_ikonu = "✅" if ai_data else "⏳"
                        
                        with st.expander(f"{durum_ikonu} | Tarih: {tarih_saat}", expanded=False):
                            c1, c2 = st.columns([1, 2])
                            with c1: st.image(p['image_url'], use_container_width=True)
                            with c2:
                                if ai_data:
                                    st.info(f"**Yorum:**\n{ai_data.get('yorum','-')}")
                                    st.warning(f"**Öneri:**\n{ai_data.get('oneri','-')}")
                                else:
                                    st.write("Analiz bekleniyor...")
                                    if st.button("Yenile", key=p['id']): st.rerun()
            except Exception as e:
                st.error(f"Hata: {e}")

# -----------------------------------------------------------------------------
# 4. GİRİŞ KONTROLÜ (EN ALT KISIM)
# -----------------------------------------------------------------------------
if st.session_state.logged_in:
    main_app()
else:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("Giriş Yap")
        email = st.text_input("E-posta")
        password = st.text_input("Şifre", type="password")
        if st.button("Giriş"):
            login_user(email, password)
