import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon
from pyproj import Transformer
import os

# 1. Configuración
st.set_page_config(page_title="Logística Rubiales v2.3", layout="wide")
st.title("🚜 Plan Logístico Rubiales v2.3")
st.caption("Coordenadas Origen Nacional (EPSG:9377)")

# 2. Función de Transformación
def proyectadas_a_latlon(este, norte):
    try:
        # Transformador de Origen Nacional (9377) a Global (4326)
        transformer = Transformer.from_crs("EPSG:9377", "EPSG:4326", always_xy=True)
        lon, lat = transformer.transform(este, norte)
        return lat, lon
    except Exception:
        return None, None

# 3. Carga de Datos (Simplificada y sin 'NoneType' errors)
@st.cache_data
def cargar_base():
    path = "COORDENADAS_GOR.xlsx"
    
    if not os.path.exists(path):
        st.error(f"Falta el archivo: {path}")
        return pd.DataFrame() # Retorna tabla vacía, no None

    try:
        # Leemos el archivo forzando el separador por si acaso
        df = pd.read_csv(path, encoding='latin-1', sep=None, engine='python')
        
        # Limpieza de nombres de columnas
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Mapeo manual por posición para evitar errores de nombres
        # 1:CLUSTER, 2:POZO, 3:ESTE, 4:NORTE
        df_coords = df.iloc[:, [1, 2, 3, 4]].copy()
        df_coords.columns = ['CLUSTER', 'POZO', 'ESTE', 'NORTE']
        
        # Convertir a números y limpiar
        df_coords['ESTE'] = pd.to_numeric(df_coords['ESTE'], errors='coerce')
        df_coords['NORTE'] = pd.to_numeric(df_coords['NORTE'], errors='coerce')
        df_coords = df_coords.dropna(subset=['ESTE', 'NORTE'])
        
        # Transformar a Lat/Lon
        # Si pyproj falla, estas columnas serán None
        results = df_coords.apply(lambda r: proyectadas_a_latlon(r['ESTE'], r['NORTE']), axis=1)
        df_coords['lat_dec'] = [r[0] for r in results]
        df_coords['lon_dec'] = [r[1] for r in results]
        
        # Agrupar
        df_final = df_coords.dropna(subset=['lat_dec']).groupby('CLUSTER').agg({
            'lat_dec': 'first', 
            'lon_dec': 'first', 
            'POZO': lambda x: ', '.join(x.astype(str).unique())
        }).reset_index()
        
        return df_final
    except Exception as e:
        st.error(f"Error procesando CSV: {e}")
        return pd.DataFrame()

# --- LÓGICA PRINCIPAL ---

df_maestro = cargar_base()

if not df_maestro.empty:
    st.sidebar.success(f"Base cargada: {len(df_maestro)} clústeres.")
    
    # Input de Usuario
    txt_input = st.sidebar.text_area("Lista de Clústeres (uno por línea):", "AGRIO-1\nCASE0015")
    nombres = [n.strip().upper() for n in re.split(r'[\n,]+', txt_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres):
        match = df_maestro[df_maestro['CLUSTER'].str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'id': i+1, 'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 'lon': match.iloc[0]['lon_dec'],
                'pozos': match.iloc[0]['POZO']
            })
        else:
            if nombre: st.sidebar.warning(f"No hallado: {nombre}")

    # Mapa
    m = folium.Map(location=[df_maestro['lat_dec'].mean(), df_maestro['lon_dec'].mean()], zoom_start=12)

    # Dibujar Ruta y Marcadores
    if len(puntos_ruta) >= 2:
        distancia_total = 0
        for j in range(len(puntos_ruta)-1):
            p1, p2 = puntos_ruta[j], puntos_ruta[j+1]
            url = f"http://router.project-osrm.org/route/v1/driving/{p1['lon']},{p1['lat']};{p2['lon']},{p2['lat']}?overview=full&geometries=geojson"
            try:
                r = requests.get(url).json()
                if r['code'] == 'Ok':
                    geom = [[c[1], c[0]] for c in r['routes'][0]['geometry']['coordinates']]
                    distancia_total += r['routes'][0]['distance'] / 1000
                    folium.PolyLine(geom, color="#2c3e50", weight=5).add_to(m)
            except: pass
        st.sidebar.metric("Distancia Total", f"{distancia_total:.2f} Km")

    for p in puntos_ruta:
        folium.Marker(
            [p['lat'], p['lon']], 
            popup=p['nombre'],
            icon=folium.Icon(color='red', icon='info-sign')
        ).add_to(m)
        
        # Etiqueta con el número de orden
        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(icon_size=(20,20), icon_anchor=(10,40),
            html=f'<div style="font-size: 12pt; color: white; background: #e74c3c; border-radius: 5px; padding: 2px 5px; font-weight: bold;">{p["id"]}</div>')
        ).add_to(m)

    st_folium(m, width=1200, height=600)
else:
    st.info("Sube el archivo CSV o revisa que los nombres de las columnas coincidan.")
