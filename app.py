import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
import os
from folium.features import DivIcon

# --- CONFIGURACIÓN DE PÁGINA (Minimalista) ---
st.set_page_config(page_title="MAPA GOR - ECOPETROL v6.0", layout="wide", initial_sidebar_state="expanded")

# --- ESTILOS CSS PERSONALIZADOS (Limpieza y Dinamismo) ---
st.markdown("""
<style>
    /* Ocultar elementos nativos pesados */
    #MainMenu, footer, header {visibility: hidden;}
    .css-1avcm0n {visibility: hidden;}
    .embeddedAppMetaBar_container__3or9D {display: none;}

    /* Contenedor del Mapa GOR - ECOPETROL */
    .block-container {padding: 0rem 1rem;}
    .reportview-container .main .block-container{padding-top: 0rem;}
    
    /* Panel lateral elegante */
    .css-1y4p8pa {
        background-color: #1a2533;
        border-right: 1px solid #2d4059;
    }
    
    /* Texto central MAPA GOR - ECOPETROL */
    .stApp h1 {
        color: #ffffff;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-weight: 700;
        text-align: center;
        font-size: 1.6rem;
        padding-top: 0.5rem;
        margin-bottom: -1rem;
        text-shadow: 1px 1px 3px black;
    }
    
    /* Métrica de distancia total sin bordes */
    div[data-testid="stMetricValue"] {
        color: #00FFCC;
        font-weight: 800;
        font-size: 1.8rem;
    }
    div[data-testid="stMetricLabel"] {
        color: #ccd6dd;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("MAPA GOR - ECOPETROL")

# --- MOTOR DE CONVERSIÓN DE COORDENADAS ---
def proyectadas_a_latlon_colombia(este, norte):
    """(Mantenemos tu lógica Magna-SIRGAS que ya funciona)"""
    try:
        a, f = 6378137.0, 1 / 298.257222101
        b = a * (1 - f)
        e2 = (a**2 - b**2) / a**2
        if este > 4000000:
            lat0_deg, lon0_deg, k0, FE, FN = 4.0, -73.0, 0.9992, 5000000.0, 2000000.0
        else:
            lat0_deg, lon0_deg, k0, FE, FN = 4.596200417, -71.077507917, 1.0, 1000000.0, 1000000.0
        
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

# --- MOTOR DE RUTAS POR TRAMO (OSRM) ---
def obtener_geometria_tramo(p1, p2):
    coords_str = f"{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}"
    url = f"http://router.project-osrm.org/route/v1/driving/{coords_str}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=5)
        res = r.json()
        if res['code'] == 'Ok':
            geom = res['routes'][0]['geometry']['coordinates']
            dist = res['routes'][0]['distance'] / 1000
            return [[lat, lon] for lon, lat in geom], dist
    except: return None, 0
    return None, 0

# --- PROCESAMIENTO DE DATOS ---
@st.cache_data
def cargar_datos_seguro(file_source):
    try:
        if isinstance(file_source, str):
            if not os.path.exists(file_source): return pd.DataFrame()
            df = pd.read_excel(file_source)
        else:
            if file_source.name.endswith('.xlsx'): df = pd.read_excel(file_source)
            else: df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_name = next((c for c in df.columns if any(k in c for k in ['CLUSTER', 'POZO', 'NAME', 'PAD'])), None)
        c_este = next((c for c in df.columns if 'ESTE' in c or 'COORDX' in c), None)
        c_norte = next((c for c in df.columns if 'NORTE' in c or 'COORDY' in c), None)
        
        if not all([c_name, c_este, c_norte]): return pd.DataFrame()

        df_f = df[[c_name, c_este, c_norte]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        
        res = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [r[0] for r in res], [r[1] for r in res]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_f.dropna(subset=['lat']).reset_index(drop=True)
    except: return pd.DataFrame()

# --- LÓGICA DE INTERFAZ LATERAL (Panel Plegable) ---
file = st.sidebar.file_uploader("Subir coordenadas (XLSX/CSV)", type=["xlsx", "csv"])

df_db = pd.DataFrame()
if file: df_db = cargar_datos_seguro(file)
elif os.path.exists("COORDENADAS_GOR.xlsx"): df_db = cargar_datos_seguro("COORDENADAS_GOR.xlsx")

puntos_ruta = []

if not df_db.empty:
    st.sidebar.success("Base de datos activa")
    entrada = st.sidebar.text_area("Orden del recorrido (uno por línea):", "CLUSTER - 33-II\nCLUSTER - 34\nCASE0021")
    nombres_in = [n.strip().upper() for n in re.split(r'[\n,]+', entrada) if n.strip()]
    
    for i, n in enumerate(nombres_in):
        key = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df_db[df_db['KEY'].str.contains(key, case=False, na=False)]
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 'n': match.iloc[0]['NAME'], 
                'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']
            })

# --- MAPA Y TRAMOS (Alto Desempeño) ---
if len(puntos_ruta) >= 2:
    # 1. Definir paleta de colores para los tramos
    colores_tramo = ["#00FFCC", "#FF007F", "#FFD700", "#FF4500", "#7CFC00"]
    num_colores = len(colores_tramo)
    
    col_mapa, col_info = st.columns([1, 4])
    
    # Mapeo y cálculo antes de renderizar
    centro_mapa = [puntos_ruta[0]['lat'], puntos_ruta[0]['lon']]
    m = folium.Map(location=centro_mapa, zoom_start=13, tiles=None)
    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', 
        attr='Google Satellite', name='Google Satellite', overlay=False, control=False
    ).add_to(m)

    distancia_total = 0
    html_info_tramos = "<h3>Detalle de Tramos</h3>"

    for i in range(len(puntos_ruta) - 1):
        p1, p2 = puntos_ruta[i], puntos_ruta[i+1]
        geometria, km = obtener_geometria_tramo(p1, p2)
        distancia_total += km
        
        # Color dinámico para el tramo
        color = colores_tramo[i % num_colores]
        
        # Construir la info lateral (HTML limpio)
        html_info_tramos += f"""
        <div style="margin-bottom: 0.5rem; padding: 0.5rem; background: #1a2533; border-radius: 4px; border-left: 4px solid {color};">
            <span style="color: #ccd6dd; font-size: 0.8rem;">Tramo {i+1}</span><br>
            <span style="color: white; font-weight: bold; font-size: 0.9rem;">{p1['n']} ➡️ {p2['n']}</span><br>
            <span style="color: {color}; font-weight: 800; font-size: 1.1rem;">{km:.2f} km</span>
        </div>
        """
        
        if geometria:
            folium.PolyLine(geometria, color=color, weight=7, opacity=0.9).add_to(m)

    with col_info:
        st_folium(m, width="100%", height=650)
        
    with col_mapa:
        st.metric("Distancia Total Recorrido", f"{distancia_total:.2f} km")
        st.write("") # Espaciado
        st.markdown(html_info_tramos, unsafe_allow_html=True)
        
        # Marcadores limpios en el mapa
        for p in puntos_ruta:
            folium.CircleMarker([p['lat'], p['lon']], radius=6, color='white', weight=2, fill=True, fill_color='red', fill_opacity=1).add_to(m)
            
            # Etiqueta de pozo elegante (sin bordes amontonados)
            folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(
                html=f'<div style="font-size: 9pt; color: white; font-weight: bold; text-shadow: 1px 1px 2px black;">{p["n"]}</div>',
                icon_size=(100,20),
                icon_anchor=(-15, 10)
            )).add_to(m)

else:
    st.info("👋 Bienvenida/o al Mapa GOR de Ecopetrol. Ingresa tu orden de recorrido en el panel lateral para planificar la ruta.")
