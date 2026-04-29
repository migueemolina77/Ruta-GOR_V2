import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon
from pyproj import Transformer
import os

st.set_page_config(page_title="Logística Rubiales v2.7", layout="wide")
st.title("🚜 Plan Logístico Rubiales v2.7")

# --- CONVERSIÓN DE EMERGENCIA ---
def convertir_manual(este, norte):
    """
    Bypass matemático para Origen Nacional (EPSG:9377) a WGS84.
    Se usa si pyproj falla por errores de inicialización en el servidor.
    """
    try:
        # Valores de referencia para Origen Nacional Colombia
        lon_0 = -73.0
        lat_0 = 4.0
        f_0 = 0.9992
        e_n = 5000000.0
        n_n = 2000000.0
        
        # Radio de la Tierra aprox en Colombia (metros)
        r_earth = 6371000.0
        
        d_n = (norte - n_n) / (r_earth * f_0)
        d_e = (este - e_n) / (r_earth * f_0 * 0.9975) # Corrección por latitud
        
        lat = lat_0 + (d_n * 180.0 / 3.14159)
        lon = lon_0 + (d_e * 180.0 / 3.14159)
        return lat, lon
    except:
        return None, None

def proyectadas_a_latlon(este, norte):
    try:
        # Intento 1: Usar la librería (Precisión total)
        transformer = Transformer.from_crs("EPSG:9377", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(float(este), float(norte))
        return lat, lon
    except:
        # Intento 2: Bypass matemático (Si el servidor falla)
        return convertir_manual(este, norte)

@st.cache_data
def cargar_base():
    path = "COORDENADAS_GOR.xlsx - data.csv"
    if not os.path.exists(path):
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Columnas: 1:CLUSTER, 3:ESTE, 4:NORTE
        df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
        df_coords.columns = ['CLUSTER', 'POZO', 'ESTE', 'NORTE']
        
        # Limpieza de espacios en los números
        df_coords['ESTE'] = pd.to_numeric(df_coords['ESTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['NORTE'] = pd.to_numeric(df_coords['NORTE'].astype(str).str.replace(' ', ''), errors='coerce')
        
        df_coords = df_coords.dropna(subset=['ESTE', 'NORTE'])
        
        results = df_coords.apply(lambda r: proyectadas_a_latlon(r['ESTE'], r['NORTE']), axis=1)
        df_coords['lat_dec'] = [r[0] if r else None for r in results]
        df_coords['lon_dec'] = [r[1] if r else None for r in results]
        
        df_final = df_coords.dropna(subset=['lat_dec']).groupby('CLUSTER').agg({
            'lat_dec': 'first', 'lon_dec': 'first', 
            'POZO': lambda x: ', '.join(x.astype(str).unique())
        }).reset_index()
        
        return df_final
    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# --- INTERFAZ ---
df_maestro = cargar_base()

if not df_maestro.empty:
    st.sidebar.success(f"Base cargada: {len(df_maestro)} clústeres")
    txt_input = st.sidebar.text_area("Ruta (Clústeres):", "AGRIO-1\nCASE0015")
    nombres = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres):
        match = df_maestro[df_maestro['CLUSTER'].str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 'lon': match.iloc[0]['lon_dec']
            })

    # Mapa
    m = folium.Map(location=[4.0, -71.8], zoom_start=11)
    
    if puntos_ruta:
        for p in puntos_ruta:
            folium.Marker(
                [p['lat'], p['lon']], 
                tooltip=p['nombre'],
                icon=folium.Icon(color='red', icon='location-dot', prefix='fa')
            ).add_to(m)
            
            folium.map.Marker(
                [p['lat'], p['lon']],
                icon=DivIcon(icon_size=(20,20), icon_anchor=(-15,20),
                html=f'<div style="font-size: 10pt; color: white; background: red; border-radius: 5px; padding: 2px 5px; font-weight: bold;">{p["id"]}</div>')
            ).add_to(m)

    st_folium(m, width=1100, height=600)
else:
    st.warning("Verifica que el archivo CSV esté en la raíz del repositorio.")
