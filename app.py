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

# Estilo para limpiar la interfaz
st.markdown("""
<style>
    .reportview-container .main .block-container{padding-top: 0rem;}
    div[data-testid="stMetricValue"] {color: #00FFCC; font-weight: 800;}
    .stApp h1 {text-align: center; color: white; text-shadow: 2px 2px 4px #000000;}
</style>
""", unsafe_allow_html=True)

st.title("MAPA GOR - ECOPETROL")

# --- FUNCIONES TÉCNICAS (CONVERSIÓN Y RUTAS) ---
def proyectadas_a_latlon_colombia(este, norte):
    try:
        a, f = 6378137.0, 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        # Origen Nacional vs Central
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
        lat = phi1 - (N1 * math.tan(phi1) / R1) * (D**2/2 - (5 + 3*math.tan(phi1)**2)*D**4/24)
        lon = lon0 + (D - (1 + 2*math.tan(phi1)**2)*D**3/6) / math.cos(phi1)
        return math.degrees(lat), math.degrees(lon)
    except: return None, None

def obtener_geometria_tramo(p1, p2):
    url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=5)
        res = r.json()
        if res['code'] == 'Ok':
            geom = res['routes'][0]['geometry']['coordinates']
            return [[lat, lon] for lon, lat in geom], res['routes'][0]['distance'] / 1000
    except: pass
    return None, 0

@st.cache_data
def cargar_datos_seguro(file_source):
    try:
        df = pd.read_excel(file_source) if hasattr(file_source, 'name') and file_source.name.endswith('.xlsx') else pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_name = next((c for c in df.columns if any(k in c for k in ['CLUSTER', 'POZO', 'NAME', 'PAD'])), None)
        c_este, c_norte = next((c for c in df.columns if 'ESTE' in c), None), next((c for c in df.columns if 'NORTE' in c), None)
        if not all([c_name, c_este, c_norte]): return pd.DataFrame()
        df_f = df[[c_name, c_este, c_norte]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        res = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [r[0] for r in res], [r[1] for r in res]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        return df_f.dropna(subset=['lat'])
    except: return pd.DataFrame()

# --- LÓGICA PRINCIPAL ---
st.sidebar.header("CONFIGURACIÓN")
file = st.sidebar.file_uploader("Subir coordenadas", type=["xlsx", "csv"])
df_db = cargar_datos_seguro(file) if file else (cargar_datos_seguro("COORDENADAS_GOR.xlsx") if os.path.exists("COORDENADAS_GOR.xlsx") else pd.DataFrame())

puntos_ruta = []
if not df_db.empty:
    st.sidebar.success("Base de datos activa")
    entrada = st.sidebar.text_area("Ruta (ej: CLUSTER-33, CLUSTER-34):", "CLUSTER-33-II\nCLUSTER-34\nCASE0021")
    for i, n in enumerate([n.strip().upper() for n in re.split(r'[\n,]+', entrada) if n.strip()]):
        key = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df_db[df_db['KEY'].str.contains(key, case=False, na=False)]
        if not match.empty:
            puntos_ruta.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']})

# --- RENDERIZADO ---
if len(puntos_ruta) >= 2:
    col_mapa, col_info = st.columns([4, 1])
    colores = ["#00FFCC", "#FF007F", "#FFD700", "#FF4500", "#7CFC00"]
    distancia_total = 0
    
    m = folium.Map(location=[puntos_ruta[0]['lat'], puntos_ruta[0]['lon']], zoom_start=13, tiles=None)
    folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google Satellite', name='Google').add_to(m)

    with col_info:
        st.write("### TRAMOS")
        for i in range(len(puntos_ruta) - 1):
            p1, p2 = puntos_ruta[i], puntos_ruta[i+1]
            geometria, km = obtener_geometria_tramo(p1, p2)
            distancia_total += km
            color = colores[i % len(colores)]
            
            # EL CAMBIO CLAVE: markdown con unsafe_allow_html=True
            st.markdown(f"""
            <div style="margin-bottom:10px; padding:8px; background:#1a2533; border-radius:5px; border-left:5px solid {color};">
                <small style="color:#888;">Tramo {i+1}</small><br>
                <b>{p1['n']} ➡️ {p2['n']}</b><br>
                <span style="color:{color}; font-size:1.2rem; font-weight:bold;">{km:.2f} km</span>
            </div>
            """, unsafe_allow_html=True)
            
            if geometria:
                folium.PolyLine(geometria, color=color, weight=7, opacity=0.85).add_to(m)

        st.divider()
        st.metric("Total", f"{distancia_total:.2f} km")

    with col_mapa:
        for p in puntos_ruta:
            folium.CircleMarker([p['lat'], p['lon']], radius=6, color='white', fill=True, fill_color='red', fill_opacity=1).add_to(m)
            folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(html=f'<div style="font-size:10pt; color:white; font-weight:bold; text-shadow:1px 1px 2px black;">{p["n"]}</div>', icon_anchor=(-15,10))).add_to(m)
        st_folium(m, width="100%", height=700)
else:
    st.info("Ingrese al menos dos puntos para iniciar.")
