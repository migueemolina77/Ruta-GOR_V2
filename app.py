import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
import os
from folium.features import DivIcon

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="MAPA GOR - ECOPETROL", layout="wide", page_icon="🦎")

# Estilo CSS para limpieza absoluta
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .main .block-container { padding-top: 2rem; }
    h1 { color: #f0f2f6; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .stAlert { border-radius: 10px; }
    .css-1kyx0rg { background-color: #1a2533; border-radius: 10px; padding: 20px; }
    .tramo-card {
        margin-bottom: 12px; padding: 15px; background: #161b22; 
        border-radius: 10px; border-left: 6px solid; border: 1px solid #30363d;
    }
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
""", unsafe_allow_html=True)

# --- ENCABEZADO ---
st.markdown("<h1 style='text-align: center;'>🦎 MAPA GOR - ECOPETROL</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #8b949e;'>Planificación Logística de Intervenciones a Pozos</p>", unsafe_allow_html=True)
st.divider()

# --- FUNCIONES TÉCNICAS (Motor Magna-SIRGAS) ---
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
        lat = phi1 - (N1 * math.tan(phi1) / R1) * (D**2/2 - (5 + 3*math.tan(phi1)**2)*D**4/24)
        lon = lon0 + (D - (1 + 2*math.tan(phi1)**2)*D**3/6) / math.cos(phi1)
        return math.degrees(lat), math.degrees(lon)
    except: return None, None

def obtener_ruta(p1, p2):
    url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=5).json()
        if r['code'] == 'Ok':
            return [[lat, lon] for lon, lat in r['routes'][0]['geometry']['coordinates']], r['routes'][0]['distance'] / 1000
    except: pass
    return None, 0

@st.cache_data
def procesar_maestro(file):
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

# --- FLUJO DEL APLICATIVO ---
archivo = st.file_uploader("📂 Por favor, cargue el archivo maestro de coordenadas (Excel/CSV):", type=["xlsx", "csv"])

if not archivo:
    st.info("👋 **Bienvenido.** Para comenzar, carga el archivo con las coordenadas de los pozos. El sistema procesará automáticamente el formato Magna-SIRGAS.")
else:
    df_db = procesar_maestro(archivo)
    if df_db.empty:
        st.error("El archivo cargado no contiene las columnas necesarias (Nombre, Este, Norte).")
    else:
        st.success(f"Base de datos cargada: {len(df_db)} puntos identificados.")
        
        col_input, col_viz = st.columns([1, 3])
        
        with col_input:
            st.subheader("Configurar Ruta")
            entrada = st.text_area("Orden de pozos (uno por línea):", help="Ejemplo: CLUSTER-34", height=150)
            lista_nombres = [n.strip().upper() for n in re.split(r'[\n,]+', entrada) if n.strip()]
            
            puntos = []
            for i, n in enumerate(lista_nombres):
                key = re.sub(r'[^a-zA-Z0-9]', '', n)
                match = df_db[df_db['KEY'].str.contains(key, case=False, na=False)]
                if not match.empty:
                    puntos.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']})
            
            if len(puntos) >= 2:
                st.divider()
                dist_acum = 0
                colores = ["#00FFCC", "#FF007F", "#FFD700", "#00BFFF", "#7CFC00"]
                for i in range(len(puntos)-1):
                    _, km = obtener_ruta(puntos[i], puntos[i+1])
                    dist_acum += km
                    c = colores[i % len(colores)]
                    st.markdown(f"""
                    <div class="tramo-card" style="border-left-color: {c};">
                        <span style="color:{c}; font-weight:bold;">{i+1} ➔ {i+2}</span><br>
                        <small style="color:white;">{puntos[i+1]['n']}</small><br>
                        <b style="color:{c};">{km:.2f} KM</b>
                    </div>
                    """, unsafe_allow_html=True)
                st.metric("DISTANCIA TOTAL", f"{dist_acum:.2f} km")

        with col_viz:
            if len(puntos) >= 2:
                m = folium.Map(location=[puntos[0]['lat'], puntos[0]['lon']], zoom_start=13, tiles=None)
                folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', attr='Google', name='Satelital').add_to(m)
                
                for i in range(len(puntos)-1):
                    geom, _ = obtener_ruta(puntos[i], puntos[i+1])
                    if geom:
                        c = colores[i % len(colores)]
                        folium.PolyLine(geom, color='white', weight=8, opacity=0.3).add_to(m)
                        folium.PolyLine(geom, color=c, weight=5, opacity=0.6).add_to(m)
                
                for p in puntos:
                    c = colores[(p['id']-1) % len(colores)]
                    label = f"""
                    <div style="text-align: center;">
                        <div style="background:{c}; color:black; border-radius:50%; width:20px; height:20px; line-height:20px; font-weight:bold; border:2px solid white; font-size:9pt;">{p['id']}</div>
                        <div style="background:rgba(14, 17, 23, 0.9); color:white; padding:3px 8px; border-radius:5px; font-size:9pt; margin-top:4px; border:1px solid {c}; white-space:nowrap;">
                            <i class="fa-solid fa-oil-well" style="color:{c};"></i> {p['n']}
                        </div>
                    </div>"""
                    folium.Marker([p['lat'], p['lon']], icon=DivIcon(html=label, icon_anchor=(10, 10))).add_to(m)
                
                st_folium(m, width="100%", height=700)
            else:
                st.info("Ingresa los nombres de los pozos en el panel de la izquierda para generar el mapa.")
