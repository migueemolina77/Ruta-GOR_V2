import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon
import os

st.set_page_config(page_title="Logística Rubiales v2.8", layout="wide")
st.title("🚜 Plan Logístico Rubiales v2.8")

# --- CONVERSIÓN MATEMÁTICA (Bypass para evitar errores de pyproj) ---
def proyectadas_a_latlon_manual(este, norte):
    """
    Convierte Origen Nacional EPSG:9377 a WGS84 usando aproximación de Gauss-Krüger.
    Ideal para evitar errores de inicialización en servidores remotos.
    """
    try:
        # Parámetros oficiales Origen Nacional Colombia
        lat_0 = 4.0
        lon_0 = -73.0
        e_n = 5000000.0
        n_n = 2000000.0
        scale = 0.9992
        r_earth = 6371000.0  # Radio medio en metros

        # Cálculo simplificado de desplazamiento
        phi = lat_0 + (norte - n_n) / (r_earth * (3.14159 / 180.0) * scale)
        # Ajuste de longitud según la latitud actual
        import math
        cos_phi = math.cos(phi * 3.14159 / 180.0)
        lam = lon_0 + (este - e_n) / (r_earth * cos_phi * (3.14159 / 180.0) * scale)
        
        return phi, lam
    except:
        return None, None

@st.cache_data
def cargar_base():
    path = "COORDENADAS_GOR.xlsx - data.csv"
    if not os.path.exists(path):
        return pd.DataFrame()

    try:
        # Carga del CSV con detección automática de separador
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Mapeo por posición (1:CLUSTER, 3:ESTE, 4:NORTE)
        df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
        df_coords.columns = ['CLUSTER', 'POZO', 'ESTE', 'NORTE']
        
        # Limpieza de datos numéricos
        df_coords['ESTE'] = pd.to_numeric(df_coords['ESTE'].astype(str).str.replace(' ', ''), errors='coerce')
        df_coords['NORTE'] = pd.to_numeric(df_coords['NORTE'].astype(str).str.replace(' ', ''), errors='coerce')
        
        df_coords = df_coords.dropna(subset=['ESTE', 'NORTE'])
        
        # Aplicar conversión manual (Evita el error de pyproj)
        results = df_coords.apply(lambda r: proyectadas_a_latlon_manual(r['ESTE'], r['NORTE']), axis=1)
        df_coords['lat_dec'] = [r[0] if r else None for r in results]
        df_coords['lon_dec'] = [r[1] if r else None for r in results]
        
        # Agrupar por Clúster
        df_final = df_coords.dropna(subset=['lat_dec']).groupby('CLUSTER').agg({
            'lat_dec': 'first', 
            'lon_dec': 'first', 
            'POZO': lambda x: ', '.join(x.astype(str).unique())
        }).reset_index()
        
        return df_final
    except Exception as e:
        st.error(f"Error cargando base: {e}")
        return pd.DataFrame()

# --- INTERFAZ DE USUARIO ---
df_maestro = cargar_base()

if not df_maestro.empty:
    st.sidebar.success(f"Base de datos cargada ({len(df_maestro)} clústeres)")
    txt_input = st.sidebar.text_area("Ingresa los Clústeres de la ruta:", "AGRIO-1\nCASE0015")
    nombres_busqueda = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]

    puntos_encontrados = []
    for i, nombre in enumerate(nombres_busqueda):
        match = df_maestro[df_maestro['CLUSTER'].str.upper() == nombre]
        if not match.empty:
            puntos_encontrados.append({
                'orden': i + 1,
                'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 
                'lon': match.iloc[0]['lon_dec']
            })
        else:
            if nombre: st.sidebar.warning(f"No se encontró: {nombre}")

    # Configuración del Mapa
    m = folium.Map(location=[4.0, -71.8], zoom_start=11)
    
    if puntos_encontrados:
        # Centrar en el primer punto
        m.location = [puntos_encontrados[0]['lat'], puntos_encontrados[0]['lon']]
        
        for p in puntos_encontrados:
            # Marcador de posición
            folium.Marker(
                [p['lat'], p['lon']],
                tooltip=f"{p['orden']}. {p['nombre']}",
                icon=folium.Icon(color='red', icon='truck', prefix='fa')
            ).add_to(m)
            
            # Etiqueta con número de orden
            folium.map.Marker(
                [p['lat'], p['lon']],
                icon=DivIcon(icon_size=(20,20), icon_anchor=(-15,20),
                html=f'<div style="font-size: 10pt; color: white; background: #c0392b; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-weight: bold; border: 1px solid white;">{p["orden"]}</div>')
            ).add_to(m)

    st_folium(m, width=1100, height=600)
else:
    st.info("No se encontró el archivo de coordenadas o la base está vacía.")
