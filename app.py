import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
import math
import os
from folium.features import DivIcon

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Logística Rubiales v4.9", layout="wide")
st.title("🚜 Planificador Logístico: Desglose de Rutas por Tramo")

# --- MOTOR DE RUTAS POR TRAMO ---
def obtener_geometria_tramo(p1, p2):
    """Calcula la ruta real entre exactamente dos puntos"""
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

# --- [FUNCIONES DE CONVERSIÓN Y CARGA - SE MANTIENEN IGUAL QUE v4.8] ---
def proyectadas_a_latlon_colombia(este, norte):
    # ... (Tu lógica Magna-SIRGAS) ...
    pass

@st.cache_data
def cargar_y_procesar_datos(file_source):
    # ... (Tu lógica de procesamiento de Excel/CSV) ...
    pass

# --- LÓGICA PRINCIPAL ---
puntos_ruta = []
file = st.sidebar.file_uploader("Cargar Coordenadas:", type=["csv", "xlsx"])
df_db = cargar_y_procesar_datos(file) if file else pd.DataFrame() # Simplificado para el ejemplo

if not df_db.empty:
    st.sidebar.success("✅ Base de Datos Lista")
    busqueda = st.sidebar.text_area("Orden de Recorrido (Pozo A, Pozo B...):", "CLUSTER - 33-II\nCLUSTER - 34\nCLUSTER - 165")
    nombres_in = [n.strip().upper() for n in re.split(r'[\n,]+', busqueda) if n.strip()]
    
    for i, n in enumerate(nombres_in):
        key = re.sub(r'[^a-zA-Z0-9]', '', n)
        match = df_db[df_db['NAME'].str.replace(r'[^a-zA-Z0-9]', '', regex=True).str.upper().str.contains(key)]
        if not match.empty:
            puntos_ruta.append({'id': i+1, 'n': match.iloc[0]['NAME'], 'lat': match.iloc[0]['lat'], 'lon': match.iloc[0]['lon']})

# --- VISUALIZACIÓN POR TRAMOS ---
if len(puntos_ruta) >= 2:
    col1, col2 = st.columns([3, 1])
    
    m = folium.Map(location=[puntos_ruta[0]['lat'], puntos_ruta[0]['lon']], zoom_start=13, tiles=None)
    folium.TileLayer(tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', 
                     attr='Google Satellite Hybrid', name='Satélite').add_to(m)

    total_general = 0
    
    with col2:
        st.subheader("📋 Hoja de Ruta")
        # Calculamos cada tramo individualmente
        for i in range(len(puntos_ruta) - 1):
            p_origen = puntos_ruta[i]
            p_destino = puntos_ruta[i+1]
            
            geometria, distancia = obtener_geometria_tramo(p_origen, p_destino)
            total_general += distancia
            
            # Mostrar info del tramo en la barra lateral
            st.write(f"**Tramo {i+1}:**")
            st.caption(f"{p_origen['n']} ➡️ {p_destino['n']}")
            st.info(f"📏 {distancia:.2f} km")
            
            # Dibujar cada tramo con un color ligeramente distinto o etiquetas
            if geometria:
                folium.PolyLine(geometria, color="#00FFCC", weight=5, opacity=0.8,
                                tooltip=f"Tramo {i+1}: {distancia:.2f} km").add_to(m)

        st.divider()
        st.metric("Distancia Total Recorrido", f"{total_general:.2f} km")

    with col1:
        # Marcadores con número de orden
        for p in puntos_ruta:
            folium.CircleMarker([p['lat'], p['lon']], radius=8, color='white', fill=True, fill_color='red').add_to(m)
            folium.map.Marker([p['lat'], p['lon']], icon=DivIcon(
                html=f'''<div style="font-family: sans-serif; color: white; font-weight: bold; 
                background: rgba(0,0,0,0.7); padding: 3px 7px; border-radius: 5px; border: 2px solid #00FFCC; width: 100px;">
                {p["id"]}. {p["n"]}</div>''')).add_to(m)
        
        st_folium(m, width="100%", height=600)
else:
    st.info("📍 Ingrese el orden de los pozos para calcular los tramos del movimiento.")
