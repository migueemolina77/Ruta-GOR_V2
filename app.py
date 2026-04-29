import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
from folium.features import DivIcon

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="LOGÍSTICA ECOPETROL V6.7", layout="wide", page_icon="🦎")

# Estilo para tarjetas y visualización limpia
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .tramo-card {
        margin-bottom: 12px; padding: 14px; background: #161b22; 
        border-radius: 10px; border-left: 6px solid; border: 1px solid #30363d;
    }
    .tramo-nombres { color: #ffffff; font-size: 0.95rem; font-weight: 600; }
    .tramo-distancia { font-size: 1.25rem; font-weight: 800; display: block; }
</style>
""", unsafe_allow_html=True)

# --- MOTOR DE COORDENADAS (Magna-SIRGAS) ---
def proyectadas_a_latlon_colombia(este, norte):
    try:
        a, f = 6378137.0, 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        # Determinación de Origen (Nacional vs Central)
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

def obtener_ruta_forzada(p1, p2):
    # Solicitamos la ruta con máxima precisión y sin simplificar geometría
    url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson&continue_straight=true"
    try:
        r = requests.get(url, timeout=5).json()
        if r['code'] == 'Ok':
            coords = [[lat, lon] for lon, lat in r['routes'][0]['geometry']['coordinates']]
            distancia = r['routes'][0]['distance'] / 1000
            
            # --- REFUERZO DE CONECTIVIDAD (LAST MILE) ---
            # Forzamos que el último punto de la línea coincida exactamente con la coordenada del pozo
            coords.append([p2['lat'], p2['lon']])
            return coords, distancia
    except: pass
    # Si el motor de rutas falla, trazamos una línea directa para no perder la referencia visual
    return [[p1['lat'], p1['lon']], [p2['lat'], p2['lon']]], 0

@st.cache_data
def cargar_db(file):
    try:
        df = pd.read_excel(file) if file.name.endswith('.xlsx') else pd.read_csv(file, encoding='latin-1', sep=None, engine='python')
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_n = next(c for c in df.columns if any(k in c for k in ['POZO', 'NAME', 'CLUSTER']))
        c_e, c_nt = next(c for c in df.columns if 'ESTE' in c), next(c for c in df.columns if 'NORTE' in c)
        df_f = df[[c_n, c_e, c_nt]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        coords = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [c[0] for c in coords], [c[1] for c in coords]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        return df_f.dropna(subset=['lat'])
    except: return pd.DataFrame()

# --- INTERFAZ ---
st.markdown("<h1 style='text-align: center;'>🦎 MAPA GOR - ECOPETROL</h1>", unsafe_allow_html=True)
archivo = st.file_uploader("📂 Carga el archivo maestro de coordenadas:", type=["xlsx", "csv"])

if archivo:
    db = cargar_db(archivo)
    col_ui, col_map = st.columns([1, 2.8])
    
    with col_ui:
        entrada = st.text_area("Orden de Pozos (Lista):", height=150, placeholder="CASE0092\nCASE0100")
        lista = [n.strip().upper() for n in re.split(r'[\n,]+', entrada) if n.strip()]
        
        puntos = []
        for i, n in enumerate(lista):
            key = re.sub(r'[^a-zA-Z0-9]', '', n)
            match = db[db['KEY'].str.contains(key, case=False, na=False)]
            if not match.empty:
                puntos.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']})

        if len(puntos) >= 2:
            st.divider()
            km_totales = 0
            colores = ["#00FFCC", "#FF007F", "#FFD700", "#00BFFF", "#7CFC00"]
            for i in range(len(puntos)-1):
                geom, km = obtener_ruta_forzada(puntos[i], puntos[i+1])
                km_totales += km
                c = colores[i % len(colores)]
                st.markdown(f"""
                <div class="tramo-card" style="border-left-color: {c};">
                    <div class="tramo-nombres">{puntos[i]['n']} ➔ {puntos[i+1]['n']}</div>
                    <span class="tramo-distancia" style="color:{c};">{km:.2f} KM</span>
                </div>""", unsafe_allow_html=True)
            st.metric("DISTANCIA TOTAL", f"{km_totales:.2f} KM")

    with col_map:
        if len(puntos) >= 2:
            m = folium.Map(location=[puntos[0]['lat'], puntos[0]['lon']], zoom_start=13, tiles=None)
            folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satélite').add_to(m)
            
            for i in range(len(puntos)-1):
                geom, _ = obtener_ruta_forzada(puntos[i], puntos[i+1])
                color_linea = colores[i % len(colores)]
                folium.PolyLine(geom, color='white', weight=7, opacity=0.4).add_to(m) # Brillo de fondo
                folium.PolyLine(geom, color=color_linea, weight=4, opacity=0.8).add_to(m)
            
            for p in puntos:
                c = colores[(p['id']-1) % len(colores)]
                lbl = f"""<div style="background:{c}; color:black; border-radius:50%; width:24px; height:24px; line-height:24px; text-align:center; font-weight:bold; border:2px solid white;">{p['id']}</div>"""
                folium.Marker([p['lat'], p['lon']], icon=DivIcon(html=lbl, icon_anchor=(12,12)), tooltip=p['n']).add_to(m)
            
            st_folium(m, width="100%", height=700)
