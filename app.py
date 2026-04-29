import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import math
import os
from folium.features import DivIcon

st.set_page_config(page_title="Logística Rubiales v3.1", layout="wide")
st.title("🚜 Plan Logístico Rubiales v3.1")

def proyectadas_a_latlon_manual(este, norte):
    try:
        # Parámetros Origen Nacional Colombia (EPSG:9377)
        lat_0, lon_0 = 4.0, -73.0
        f_este, f_norte = 5000000.0, 2000000.0
        scale, r_earth = 0.9992, 6378137.0

        d_norte = (norte - f_norte) / scale
        d_este = (este - f_este) / scale

        lat = lat_0 + (d_norte / r_earth) * (180.0 / math.pi)
        lon = lon_0 + (d_este / (r_earth * math.cos(math.radians(lat_0)))) * (180.0 / math.pi)
        
        return lat, lon
    except:
        return None, None

@st.cache_data
def cargar_base():
    path = "COORDENADAS_GOR.xlsx - data.csv"
    if not os.path.exists(path): return pd.DataFrame()
    try:
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Seleccionar columnas clave
        df_coords = df.iloc[:, [1, 3, 4]].copy()
        df_coords.columns = ['CLUSTER', 'ESTE', 'NORTE']
        
        # Limpiar números
        df_coords['ESTE'] = pd.to_numeric(df_coords['ESTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['NORTE'] = pd.to_numeric(df_coords['NORTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords = df_coords.dropna()

        # Convertir a Lat/Lon
        lats, lons = [], []
        for _, row in df_coords.iterrows():
            lt, ln = proyectadas_a_latlon_manual(row['ESTE'], row['NORTE'])
            lats.append(lt); lons.append(ln)
        
        df_coords['lat_dec'] = lats
        df_coords['lon_dec'] = lons
        
        # Crear una columna de búsqueda limpia (sin guiones ni espacios)
        df_coords['SEARCH_KEY'] = df_coords['CLUSTER'].astype(str).str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper()
        
        return df_coords.dropna(subset=['lat_dec']).groupby('CLUSTER').first().reset_index()
    except Exception as e:
        st.error(f"Error cargando archivo: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
df_maestro = cargar_base()

st.sidebar.header("📍 Planificador de Ruta")
txt_input = st.sidebar.text_area("Lista de Clústeres (uno por línea):", "AGRIO-1\nCASE0015")

# Procesar búsqueda
puntos_ruta = []
if not df_maestro.empty:
    nombres_busqueda = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]
    
    for i, nombre in enumerate(nombres_busqueda):
        # Buscamos de forma flexible (quitando caracteres especiales)
        key_busqueda = re.sub(r'[^a-zA-Z0-9]', '', nombre)
        match = df_maestro[df_maestro['SEARCH_KEY'] == key_busqueda]
        
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 
                'nombre': match.iloc[0]['CLUSTER'], 
                'lat': match.iloc[0]['lat_dec'], 
                'lon': match.iloc[0]['lon_dec']
            })
        else:
            if nombre: st.sidebar.warning(f"❓ No encontrado: {nombre}")

# Configuración del mapa
centro_lat, centro_lon = 3.99, -71.73 # Rubiales
if puntos_ruta:
    centro_lat = sum(p['lat'] for p in puntos_ruta) / len(puntos_ruta)
    centro_lon = sum(p['lon'] for p in puntos_ruta) / len(puntos_ruta)

m = folium.Map(location=[centro_lat, centro_lon], zoom_start=12)

for p in puntos_ruta:
    folium.Marker(
        [p['lat'], p['lon']], 
        tooltip=f"{p['id']}. {p['nombre']}",
        icon=folium.Icon(color='red', icon='truck', prefix='fa')
    ).add_to(m)
    
    folium.map.Marker(
        [p['lat'], p['lon']],
        icon=DivIcon(icon_size=(25,25), icon_anchor=(-15,25),
        html=f'<div style="font-size: 10pt; color: white; background: #c0392b; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 1px solid white;">{p["id"]}</div>')
    ).add_to(m)

# Mostrar mapa
st_folium(m, width=1100, height=600, key="mapa_final")

# Tabla de depuración (solo si hay puntos)
if puntos_ruta:
    st.subheader("📋 Resumen de la Ruta")
    st.table(pd.DataFrame(puntos_ruta)[['id', 'nombre', 'lat', 'lon']])
elif not df_maestro.empty:
    st.info("Ingresa nombres de clústeres en el panel izquierdo.")
    with st.expander("Ver nombres disponibles en la base"):
        st.write(", ".join(df_maestro['CLUSTER'].unique()[:50]) + "...")
