import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime
import extra_streamlit_components as stx

# --- 1. הגדרות עמוד ועיצוב (RTL + Mobile Friendly) ---
st.set_page_config(page_title="מועדון סודה PRO", layout="centered", page_icon="🥤")

st.markdown("""
    <style>
    .stApp { direction: rtl; text-align: right; }
    div[data-testid="stForm"] { direction: rtl; }
    .stTabs [data-baseweb="tab-list"] { direction: rtl; justify-content: center; }
    .centered-text { text-align: center; width: 100%; }
    .balance-box {
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        font-weight: bold;
        font-size: 28px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    /* שיפור נראות כפתורים במובייל */
    .stButton>button { width: 100%; border-radius: 10px; height: 3em; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. חיבור ל-Supabase וניהול עוגיות ---
@st.cache_resource
def init_supabase() -> Client:
    # ודא שהגדרת SUPABASE_URL ו-SUPABASE_KEY ב-Secrets של Streamlit
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()
cookie_manager = stx.CookieManager()

# --- 3. פונקציות שליפה וחישוב נתונים ---
def get_all_data():
    try:
        # שליפת נתונים מהטבלאות ב-Supabase
        users = supabase.table("users").select("*").execute().data
        trans = supabase.table("transactions").select("*").order("timestamp", desc=True).execute().data
        inv = supabase.table("inventory").select("*").execute().data
        settings = supabase.table("settings").select("*").execute().data
        
        u_df = pd.DataFrame(users) if users else pd.DataFrame(columns=['name', 'pin', 'role'])
        t_df = pd.DataFrame(trans) if trans else pd.DataFrame(columns=['timestamp', 'name', 'type', 'amount', 'status', 'notes'])
        i_df = pd.DataFrame(inv) if inv else pd.DataFrame(columns=['timestamp', 'quantity'])
        
        # שליפת מחיר בקבוק מהגדרות
        price = 2.5
        if settings:
            for s in settings:
                if s['key'] == 'bottle_price':
                    price = float(s['value'])
                    
        return u_df, t_df, price, i_df
    except Exception as e:
        st.error(f"שגיאה בטעינת נתונים מ-Supabase: {e}")
        return pd.DataFrame(), pd.DataFrame(), 2.5, pd.DataFrame()

users_df, trans_df, bottle_price, inv_df = get_all_data()

def calculate_balance(name, df):
    if df.empty or name not in df['name'].values: return 0.0, 0.0
    u_t = df[df["name"] == name]
    purchases = u_t[u_t["type"] == "purchase"]["amount"].sum()
    payments = u_t[(u_t["type"] == "payment") & (u_t["status"] == "completed")]["amount"].sum()
    adjustments = u_t[u_t["type"] == "adjustment"]["amount"].sum()
    pending = u_t[(u_t["type"] == "payment") & (u_t["status"] == "pending")]["amount"].sum()
    # יתרה = הפקדות - (קניות + התאמות)
    return (payments - (purchases + adjustments)), pending

# --- 4. פונקציות עדכון (Inserts / Updates) ---
def db_add_transaction(name, t_type, amount, status="completed", notes=""):
    data = {
        "name": name, "type": t_type, "amount": amount, 
        "status": status, "notes": notes, 
        "timestamp": datetime.now().isoformat()
    }
    supabase.table("transactions").insert(data).execute()
    st.cache_data.clear()
    st.rerun()

def db_update_inventory(qty_change):
    data = {"quantity": qty_change, "timestamp": datetime.now().isoformat()}
    supabase.table("inventory").insert(data).execute()
    st.cache_data.clear()
    st.rerun()

def db_update_price(new_price):
    supabase.table("settings").update({"value": new_price}).eq("key", "bottle_price").execute()
    st.cache_data.clear()
    st.rerun()

# --- 5. לוגיקת התחברות ---
if "logout_in_progress" not in st.session_state:
    st.session_state.logout_in_progress = False

if "user" not in st.session_state and not st.session_state.logout_in_progress:
    saved_name = cookie_manager.get(cookie="soda_user_name")
    if saved_name and not users_df.empty:
        u_match = users_df[users_df["name"] == saved_name]
        if not u_match.empty:
            st.session_state.user = u_match.iloc[0].to_dict()
            st.rerun()

# --- 6. ממשק המשתמש ---
if "user" not in st.session_state:
    st.markdown("<h1 class='centered-text'>🥤 מועדון סודה</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            u_list = users_df["name"].tolist() if not users_df.empty else []
            login_name = st.selectbox("מי מגיע לשתות?", u_list, index=None, placeholder="בחר שם...")
            login_pin = st.text_input("קוד אישי (PIN)", type="password")
            if st.form_submit_button("כניסה למערכת", use_container_width=True):
                if login_name:
                    u_match = users_df[users_df["name"] == login_name]
                    if not u_match.empty and str(login_pin).strip() == u_match.iloc[0]["pin"]:
                        st.session_state.user = u_match.iloc[0].to_dict()
                        st.session_state.logout_in_progress = False
                        cookie_manager.set("soda_user_name", login_name, expires_at=datetime.now().replace(year=datetime.now().year + 1))
                        st.cache_data.clear()
                        st.rerun()
                    else: st.error("קוד שגוי.")
else:
    curr_user = st.session_state.user
    is_admin = curr_user.get('role') == 'admin'
    
    # טאבים עם זיכרון
    tabs = st.tabs(["👤 החשבון שלי", "🛠️ ניהול"]) if is_admin else [st.container()]

    with tabs[0]:
        st.markdown(f"<h2 class='centered-text'>אהלן, {curr_user['name']}</h2>", unsafe_allow_html=True)
        
        balance, pending = calculate_balance(curr_user['name'], trans_df)
        color = "#28a745" if balance >= 0 else "#dc3545"
        
        st.markdown(f"""
            <div class="balance-box" style="color: {color}; border: 2px solid {color}; background-color: {color}10;">
                יתרה בחשבון: ₪{balance:.2f}
            </div>
            """, unsafe_allow_html=True)
        
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("מחיר בקבוק", f"₪{bottle_price}")
        if pending > 0: col_m2.warning(f"ממתין לאישור: ₪{pending}")

        st.divider()

        # קנייה מרובה
        with st.expander("🥤 רכישת סודה", expanded=True):
            cq1, cq2 = st.columns([1, 2])
            qty = cq1.number_input("כמות", min_value=1, value=1, step=1)
            if cq2.button(f"אשר רכישה (₪{qty*bottle_price:.2f})", type="primary"):
                db_add_transaction(curr_user['name'], "purchase", qty*bottle_price)
        
        # הפקדה
        with st.expander("💳 הפקדת כסף"):
            with st.form("pay_f", clear_on_submit=True):
                p_amt = st.number_input("סכום להפקדה (₪)", min_value=1.0, value=20.0, step=1.0)
                if st.form_submit_button("שלח בקשה למנהל"):
                    db_add_transaction(curr_user['name'], "payment", p_amt, status="pending")

        if st.button("🚪 התנתקות"):
            cookie_manager.delete("soda_user_name")
            st.session_state.logout_in_progress = True
            if "user" in st.session_state: del st.session_state.user
            st.cache_data.clear()
            st.rerun()

    if is_admin:
        with tabs[1]:
            st.markdown("<h2 class='centered-text'>ניהול מערכת</h2>", unsafe_allow_html=True)
            
            # 1. אישור הפקדות
            st.subheader("💳 אישור הפקדות")
            p_df = trans_df[trans_df["status"] == "pending"] if not trans_df.empty else pd.DataFrame()
            if not p_df.empty:
                for idx, row in p_df.iterrows():
                    ca, cb = st.columns([3, 1])
                    ca.write(f"**{row['name']}**: הפקיד ₪{row['amount']}")
                    if cb.button("אשר ✅", key=f"ap_{row['id']}"):
                        supabase.table("transactions").update({"status": "completed"}).eq("id", row['id']).execute()
                        st.cache_data.clear()
                        st.rerun()
            else: st.info("אין הפקדות ממתינות.")

            st.divider()

            # 2. מלאי ומחיר
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("📦 מלאי")
                bottles_taken = len(trans_df[trans_df['type'] == 'purchase']) if not trans_df.empty else 0
                stock = inv_df['quantity'].sum() - bottles_taken if not inv_df.empty else 0
                st.metric("במקרר", int(stock))
                with st.popover("עדכן מלאי", use_container_width=True):
                    qc = st.number_input("שינוי (+/-)", value=0, step=1)
                    if st.button("בצע עדכון"): db_update_inventory(qc)
            
            with col_b:
                st.subheader("💰 הגדרות")
                st.metric("מחיר נוכחי", f"₪{bottle_price}")
                with st.popover("שנה מחיר", use_container_width=True):
                    np = st.number_input("מחיר חדש", value=bottle_price, step=0.5)
                    if st.button("שמור"): db_update_price(np)

            st.divider()

            # 3. עדכון יתרה ידני
            with st.expander("🔄 עדכון יתרה ידני"):
                with st.form("adj_f"):
                    t_user = st.selectbox("בחר משתמש", users_df["name"].tolist())
                    t_amt = st.number_input("סכום (חיובי מוסיף כסף, שלילי מוריד)", value=0.0, step=1.0)
                    t_note = st.text_input("סיבה")
                    if st.form_submit_button("בצע עדכון"):
                        if t_amt != 0:
                            db_add_transaction(t_user, "adjustment", -t_amt, notes=t_note)

            # 4. טבלת יתרות כללית
            st.subheader("📊 טבלת יתרות")
            if not users_df.empty:
                all_balances = []
                for _, u in users_df.iterrows():
                    bal, _ = calculate_balance(u['name'], trans_df)
                    all_balances.append({"שם": u["name"], "יתרה (₪)": round(bal, 2)})
                st.dataframe(pd.DataFrame(all_balances).sort_values("יתרה (₪)", ascending=False), use_container_width=True, hide_index=True)
