import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
import os
from folium.features import DivIcon

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="MAPA GOR - ECOPETROL", layout="wide")

# Estilos personalizados: Tarjetas y etiquetas
st.markdown("""
<style>
    .reportview-container .main .block-container{padding-top: 0rem;}
    .stApp h1 {text-align: center; color: white; font-size: 1.6rem; margin-bottom: 0;}
    .tramo-card {
        margin-bottom: 10px; padding: 12px; background: #111b27; 
        border-radius: 8px; border-top: 4px solid;
    }
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
""", unsafe_allow_html=True)

st.title("LOGÍSTICA DE SUB-SUELO: RUBIALES")

# --- MOTOR DE CÁLCULO (Magna-SIRGAS) ---
def proyectadas_a_latlon_colombia(este, norte):
    try:
        a, f = 6378137.0, 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        lat0_deg, lon0_deg, k0, FE, FN = (4.0, -73.0, 0.9992, 5000000.0, 2000000.0) if este > 4000000 else (4.596200417, -71.077507917, 1.0, 1000000.0, 1000000.0)
        lat0, lon0 = math.radians(lat0_deg), math.radians(lon0_deg)
        M0 = a * ((1 - e2/4 - 3*e2**2/64)*lat0 - (3*e2/8 + 3*e2**2/32)*math.sin(2*lat0) + (15*e2**2/256)*math.sin(4*lat0))
        M = M0 + (norte - FN) / k0
        mu = M / (a * (1 - e2/4 - 3*e2**2/64))
        e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
        phi1 = mu + (3*e1/2 - 27*e1**3/32)*math.sin(2*mu) + (21*e1**2/16 - 55*e1**4/32)*math.sin(4*mu)
        N1 = a / math.sqrt(1 - e2 * math.sin(phi1)**2)
        R1 = a * (1 - e2) / (1 - e2 * math.sin(phi1)**2)**1.5
        D = (este - FE) / (N1 * k0)
        lat, lon = phi1 - (N1 * math.tan(phi1) / R1) * (D**2/2 - (5 + 3*math.tan(phi1)**2)*D**4/24), lon0 + (D - (1 + 2*math.tan(phi1)**2)*D**3/6) / math.cos(phi1)
        return math.degrees(lat), math.degrees(lon)
    except: return None, None

def obtener_geometria_tramo(p1, p2):
    url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=5).json()
        if r['code'] == 'Ok':
            return [[lat, lon] for lon, lat in r['routes'][0]['geometry']['coordinates']], r['routes'][0]['distance'] / 1000
    except: pass
    return None, 0

@st.cache_data
def cargar_db(file_source):
    try:
        df = pd.read_excel(file_source) if hasattr(file_source, 'name') and file_source.name.endswith('.xlsx') else pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_n, c_e, c_nt = next(c for c in df.columns if any(k in c for k in ['POZO', 'NAME', 'CLUSTER'])), next(c for c in df.columns if 'ESTE' in c), next(c for c in df.columns if 'NORTE' in c)
        df_f = df[[c_n, c_e, c_nt]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        res = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [r[0] for r in res], [r[1] for r in res]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        return df_f.dropna(subset=['lat'])
    except: return pd.DataFrame()

# --- PANEL LATERAL ---
file = st.sidebar.file_uploader("Actualizar Coordenadas", type=["xlsx", "csv"])
df_db = cargar_db(file) if file else (cargar_db("COORDENADAS_GOR.xlsx") if os.path.exists("COORDENADAS_GOR.xlsx") else pd.DataFrame())

puntos_ruta = []
if not df_db.empty:
    entrada = st.sidebar.text_area("Secuencia de Operación:", "CLUSTER-33-II\nCLUSTER-34\nCASE0021")
    for i, n in enumerate([n.strip().upper() for n in re.split(r'[\n,]+', entrada) if n.strip()]):
        match = df_db[df_db['KEY'].str.contains(re.sub(r'[^a-zA-Z0-9]', '', n), case=False, na=False)]
        if not match.empty:
            puntos_ruta.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']})

# --- MAPA Y LOGÍSTICA ---
if len(puntos_ruta) >= 2:
    col_mapa, col_info = st.columns([3.8, 1.2])
    colores = ["#00FFCC", "#FF007F", "#FFD700", "#00BFFF", "#ADFF2F"]
    dist_total = 0
    
    m = folium.Map(location=[puntos_ruta[0]['lat'], puntos_ruta[0]['lon']], zoom_start=13, tiles=None)
    folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google Satellite', name='Satelital').add_to(m)

    with col_info:
        st.markdown("<h4 style='color:#00FFCC;'>Resumen de Tramos</h4>", unsafe_allow_html=True)
        for i in range(len(puntos_ruta) - 1):
            p1, p2 = puntos_ruta[i], puntos_ruta[i+1]
            geom, km = obtener_geometria_tramo(p1, p2)
            dist_total += km
            c = colores[i % len(colores)]
            
            st.markdown(f"""
            <div class="tramo-card" style="border-color: {c};">
                <small style="color:{c};">ORDEN {i+1}</small><br>
                <b style="color:white; font-size:0.85rem;">{p1['n']} ➔ {p2['n']}</b><br>
                <span style="color:{c}; font-size:1.2rem; font-weight:bold;">{km:.2f} KM</span>
            </div>
            """, unsafe_allow_html=True)
            
            if geom:
                # Línea con transparencia (0.6) y borde de separación (weight=9 blanco abajo)
                folium.PolyLine(geom, color='white', weight=9, opacity=0.3).add_to(m)
                folium.PolyLine(geom, color=c, weight=6, opacity=0.6).add_to(m)

        st.metric("DISTANCIA TOTAL", f"{dist_total:.2f} km")

    with col_mapa:
        for p in puntos_ruta:
            # Marcador con ícono de Pozo / Machín
            icono_pozo = f"""
            <div style="text-align: center;">
                <div style="background:{colores[(p['id']-1)%len(colores)]}; color:black; border-radius:50%; width:22px; height:22px; line-height:22px; font-weight:bold; border:2px solid white; font-size:10pt;">{p['id']}</div>
                <div style="background:rgba(0,0,0,0.8); color:white; padding:2px 5px; border-radius:3px; font-size:9pt; margin-top:3px; white-space:nowrap; border:1px solid #555;">
                    <i class="fa-solid fa-tower-broadcast" style="color:#00FFCC; font-size:8pt;"></i> {p['n']}
                </div>
            </div>"""
            
            folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(html=icono_pozo, icon_anchor=(11, 11))).add_to(m)
        st_folium(m, width="100%", height=750)
else:
    st.info("Ingresa los pozos en el panel lateral para trazar la logística de intervención.")
