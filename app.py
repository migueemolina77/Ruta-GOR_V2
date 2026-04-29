import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v3.5", layout="wide")
st.title("🚜 Sistema Logístico Rubiales v3.5")

def proyectadas_a_latlon_manual(este, norte):
    try:
        lat_0, lon_0 = 4.0, -73.0
        f_este, f_norte = 5000000.0, 2000000.0
        scale, r_earth = 0.9992, 6378137.0
        d_norte = (norte - f_norte) / scale
        d_este = (este - f_este) / scale
        lat = lat_0 + (d_norte / r_earth) * (180.0 / math.pi)
        lon = lon_0 + (d_este / (r_earth * math.cos(math.radians(lat_0)))) * (180.0 / math.pi)
        return lat, lon
    except: return None, None

# --- GESTIÓN DE DATOS ---
st.sidebar.header("📁 Carga de Datos")
archivo_subido = st.sidebar.file_uploader("Si el mapa está vacío, sube el CSV aquí:", type=["csv"])

@st.cache_data
def procesar_datos(file_source):
    try:
        df = pd.read_csv(file_source, encoding='latin-1', sep=None, engine='python')
        # Extraer: CLUSTER (col 1), ESTE (col 3), NORTE (col 4)
        df_coords = df.iloc[:, [1, 3, 4]].copy()
        df_coords.columns = ['NAME', 'E', 'N']
        
        df_coords['E'] = pd.to_numeric(df_coords['E'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['N'] = pd.to_numeric(df_coords['N'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords = df_coords.dropna()

        lats, lons = [], []
        for _, row in df_coords.iterrows():
            lt, ln = proyectadas_a_latlon_manual(row['E'], row['N'])
            lats.append(lt); lons.append(ln)
        
        df_coords['lat'] = lats
        df_coords['lon'] = lons
        df_coords['KEY'] = df_coords['NAME'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        return df_coords.dropna(subset=['lat']).groupby('NAME').first().reset_index()
    except Exception as e:
        st.error(f"Error al procesar: {e}")
        return pd.DataFrame()

# Intentar cargar desde archivo del repo o desde el subido
df_maestro = pd.DataFrame()
path_auto = "COORDENADAS_GOR.xlsx - data.csv"

if archivo_subido is not None:
    df_maestro = procesar_datos(archivo_subido)
elif os.path.exists(path_auto):
    df_maestro = procesar_datos(path_auto)

# --- INTERFAZ Y MAPA ---
puntos_finales = []
if not df_maestro.empty:
    st.sidebar.success("✅ Datos cargados correctamente")
    txt_busqueda = st.sidebar.text_area("Buscar Clústeres (uno por línea):", "")
    
    # Lógica de búsqueda
    nombres = [n.strip().upper() for n in re.split(r'[\n,]+', txt_busqueda) if n.strip()]
    for i, n in enumerate(nombres):
        key = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df_maestro[df_maestro['KEY'] == key]
        if not match.empty:
            puntos_finales.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon'], 'color': 'red'})

    # Si no hay búsqueda, mostrar los primeros 5 como prueba
    if not puntos_finales:
        for i, row in df_maestro.head(5).iterrows():
            puntos_finales.append({'id': '•', 'n': row['NAME'], 'lat': row['lat'], 'lon': row['lon'], 'color': 'blue'})

# Configuración del Mapa
m = folium.Map(location=[3.99, -71.73], zoom_start=11)
if puntos_finales:
    m.location = [puntos_finales[0]['lat'], puntos_finales[0]['lon']]
    for p in puntos_finales:
        folium.Marker([p['lat'], p['lon']], tooltip=p['n'], icon=folium.Icon(color=p['color'])).add_to(m)
        folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(icon_size=(20,20), icon_anchor=(-15,20),
            html=f'<div style="font-size: 9pt; color: white; background: {p["color"]}; border-radius: 4px; padding: 2px 5px;">{p["n"]}</div>')).add_to(m)

st_folium(m, width=1100, height=600, key="mapa_v35")

# Lista desplegable de ayuda
if not df_maestro.empty:
    with st.expander("🔍 Ver todos los Clústeres detectados en el archivo"):
        st.write(df_maestro['NAME'].sort_values().tolist())
else:
    st.warning("⚠️ No se detectó el archivo automáticamente. Por favor, súbelo manualmente en el panel de la izquierda.")
