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
st.set_page_config(page_title="Logística Rubiales v5.0", layout="wide")
st.title("🚜 Planificador Logístico: Desglose de Rutas por Tramo")

# --- 1. MOTOR DE CONVERSIÓN (MAGNA-SIRGAS) ---
def proyectadas_a_latlon_colombia(este, norte):
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
    except:
        return None, None

# --- 2. MOTOR DE RUTAS POR TRAMO (OSRM) ---
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
    except:
        return None, 0
    return None, 0

# --- 3. PROCESAMIENTO SEGURO DE DATOS ---
@st.cache_data
def cargar_datos_seguro(file_source):
    try:
        if isinstance(file_source, str):
            if not os.path.exists(file_source): return pd.DataFrame()
            df = pd.read_excel(file_source)
        else:
            if file_source.name.endswith('.xlsx'):
                df = pd.read_excel(file_source)
            else:
                df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        
        # Estandarizar columnas
        df.columns = [re.sub(r'[^a-zA-Z]', '', str(c)).upper() for c in df.columns]
        c_name = next((c for c in df.columns if any(k in c for k in ['CLUSTER', 'POZO', 'NAME', 'PAD'])), None)
        c_este = next((c for c in df.columns if 'ESTE' in c or 'COORDX' in c), None)
        c_norte = next((c for c in df.columns if 'NORTE' in c or 'COORDY' in c), None)
        
        if not all([c_name, c_este, c_norte]): return pd.DataFrame()

        df_f = df[[c_name, c_este, c_norte]].copy().dropna()
        df_f.columns = ['NAME', 'E', 'N']
        
        # Conversión masiva
        res = df_f.apply(lambda r: proyectadas_a_latlon_colombia(r['E'], r['N']), axis=1)
        df_f['lat'], df_f['lon'] = [r[0] for r in res], [r[1] for r in res]
        df_f['KEY'] = df_f['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_f.dropna(subset=['lat']).reset_index(drop=True)
    except:
        return pd.DataFrame()

# --- 4. LÓGICA DE INTERFAZ ---
st.sidebar.header("Carga de Datos")
archivo_subido = st.sidebar.file_uploader("Subir coordenadas:", type=["xlsx", "csv"])

# Inicializar df_db SIEMPRE para evitar el AttributeError
df_db = pd.DataFrame()

if archivo_subido:
    df_db = cargar_datos_seguro(archivo_subido)
elif os.path.exists("COORDENADAS_GOR.xlsx"):
    df_db = cargar_datos_seguro("COORDENADAS_GOR.xlsx")

puntos_ruta = []

if not df_db.empty:
    st.sidebar.success("✅ Base de datos activa")
    entrada = st.sidebar.text_area("Orden del recorrido (uno por línea):", "CLUSTER - 33-II\nCLUSTER - 34")
    nombres_in = [n.strip().upper() for n in re.split(r'[\n,]+', entrada) if n.strip()]
    
    for i, n in enumerate(nombres_in):
        key = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df_db[df_db['KEY'].str.contains(key, case=False, na=False)]
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 'n': match.iloc[0]['NAME'], 
                'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']
            })

# --- 5. RENDERIZADO DEL MAPA Y TRAMOS ---
if len(puntos_ruta) >= 2:
    col_mapa, col_info = st.columns([3, 1])
    
    with col_info:
        st.subheader("📋 Detalle de Tramos")
        distancia_total = 0
        
        m = folium.Map(location=[puntos_ruta[0]['lat'], puntos_ruta[0]['lon']], zoom_start=13, tiles=None)
        folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', 
                         attr='Google Satellite', name='Google Satellite').add_to(m)

        for i in range(len(puntos_ruta) - 1):
            p1, p2 = puntos_ruta[i], puntos_ruta[i+1]
            geometria, km = obtener_geometria_tramo(p1, p2)
            distancia_total += km
            
            with st.expander(f"Tramo {i+1}: {p1['n']} ➡️ {p2['n']}", expanded=True):
                st.write(f"**Distancia:** {km:.2f} km")
            
            if geometria:
                folium.PolyLine(geometria, color="#00FFCC", weight=6, opacity=0.8).add_to(m)

        st.divider()
        st.metric("Distancia Total", f"{distancia_total:.2f} km")

    with col_mapa:
        for p in puntos_ruta:
            folium.CircleMarker([p['lat'], p['lon']], radius=7, color='white', fill=True, fill_color='red').add_to(m)
            folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(html=f'<div style="font-size: 10pt; color: white; font-weight: bold; background: rgba(0,0,0,0.6); padding: 2px 5px; border-radius: 3px;">{p["id"]}. {p["n"]}</div>')).add_to(m)
        
        st_folium(m, width="100%", height=650)
else:
    st.info("💡 Para comenzar, asegúrate de tener cargado el archivo de coordenadas e ingresa al menos dos puntos en la 'Ruta de Trabajo'.")
