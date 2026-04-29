import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon
import pyproj
from pyproj import Transformer
import os

st.set_page_config(page_title="Logística Rubiales v2.6", layout="wide")
st.title("🚜 Plan Logístico Rubiales v2.6")

# --- SOLUCIÓN PARA EL ERROR DE INITIALIZATION ---
# Forzamos a pyproj a usar su base de datos interna o descargarla si es necesario
try:
    pyproj.network.set_network_enabled(active=True)
except:
    pass

def proyectadas_a_latlon(este, norte):
    """
    Convierte coordenadas Magna-SIRGAS Origen Nacional (9377) a WGS84 (4326).
    Se inicializa dentro de la función para evitar el ValueError de inicialización.
    """
    try:
        # Inicialización local para evitar el error de 'not initialized'
        trans = Transformer.from_crs("EPSG:9377", "EPSG:4326", always_xy=True)
        lon, lat = trans.transform(float(este), float(norte))
        return lat, lon
    except Exception as e:
        # Si falla pyproj, devolvemos None para no romper el código
        return None, None

@st.cache_data
def cargar_base():
    path = "COORDENADAS_GOR.xlsx - data.csv"
    if not os.path.exists(path):
        return pd.DataFrame()

    try:
        # Leemos con separador automático
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Seleccionar por posición para seguridad
        df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
        df_coords.columns = ['CLUSTER', 'POZO', 'ESTE', 'NORTE']
        
        # Limpiar números
        df_coords['ESTE'] = pd.to_numeric(df_coords['ESTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['NORTE'] = pd.to_numeric(df_coords['NORTE'].astype(str).str.replace(' ', ''), errors='coerce')
        
        df_coords = df_coords.dropna(subset=['ESTE', 'NORTE'])
        
        # Transformación con manejo de errores interno
        lats, lons = [], []
        for _, row in df_coords.iterrows():
            res = proyectadas_a_latlon(row['ESTE'], row['NORTE'])
            if res:
                lats.append(res[0])
                lons.append(res[1])
            else:
                lats.append(None)
                lons.append(None)
        
        df_coords['lat_dec'] = lats
        df_coords['lon_dec'] = lons
        
        # Filtrar solo los que tengan coordenadas válidas
        df_final = df_coords.dropna(subset=['lat_dec', 'lon_dec'])
        
        return df_final.groupby('CLUSTER').agg({
            'lat_dec': 'first', 
            'lon_dec': 'first', 
            'POZO': lambda x: ', '.join(x.astype(str).unique())
        }).reset_index()
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
df_maestro = cargar_base()

if not df_maestro.empty:
    st.sidebar.success(f"Base cargada: {len(df_maestro)} clústeres")
    txt_input = st.sidebar.text_area("Ruta de Clústeres:", "AGRIO-1\nCASE0015")
    nombres = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres):
        match = df_maestro[df_maestro['CLUSTER'].str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 'lon': match.iloc[0]['lon_dec']
            })
        else:
            if nombre: st.sidebar.warning(f"⚠️ '{nombre}' no encontrado")

    # Mapa centrado en el promedio o en Rubiales
    if puntos_ruta:
        center_lat = sum(p['lat'] for p in puntos_ruta) / len(puntos_ruta)
        center_lon = sum(p['lon'] for p in puntos_ruta) / len(puntos_ruta)
    else:
        center_lat, center_lon = 4.01, -71.74 # Rubiales Aprox

    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

    for p in puntos_ruta:
        folium.Marker(
            [p['lat'], p['lon']], 
            tooltip=p['nombre'],
            icon=folium.Icon(color='red', icon='location-pin')
        ).add_to(m)
        
        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(icon_size=(20,20), icon_anchor=(-10,20),
            html=f'<div style="font-size: 10pt; color: white; background: black; border-radius: 50%; width: 22px; height: 22px; text-align: center; font-weight: bold; border: 1px solid white;">{p["id"]}</div>')
        ).add_to(m)

    st_folium(m, width=1100, height=600)
else:
    st.info("Esperando carga de base de datos o archivo ausente.")
