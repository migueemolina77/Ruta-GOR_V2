import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon

# Configuración de página
st.set_page_config(page_title="Logística Rubiales & CASE - Etapa 2", layout="wide")

# 1. Función para convertir coordenadas (por si vienen en formato texto)
def dms_to_decimal(dms_str):
    try:
        if pd.isna(dms_str) or str(dms_str).strip() == "": return None
        if isinstance(dms_str, (int, float)): return float(dms_str)
        # Extraer números por si hay símbolos de grados
        parts = re.findall(r"[-+]?\d*\.\d+|\d+", str(dms_str))
        if len(parts) == 1: return float(parts[0])
        if len(parts) < 3: return None
        deg, minu, sec = map(float, parts)
        decimal = deg + (minu / 60) + (sec / 3600)
        if any(char in str(dms_str).upper() for char in ['S', 'W', 'O']):
            decimal *= -1
        return decimal
    except:
        return None

# 2. Carga del archivo "COORDENADAS GOR" (Sin celdas combinadas)
@st.cache_data
def cargar_base_coordenadas(file_path):
    # Cargamos el archivo normalmente (la fila 1 es el encabezado)
    df = pd.read_csv(file_path, encoding='latin-1')
    
    # Limpiamos espacios en blanco en los nombres de las columnas por seguridad
    df.columns = df.columns.str.strip()
    
    # Creamos un DataFrame limpio usando los nombres exactos de tu nuevo archivo
    # Usamos 'LOCACION' como el Clúster
    df_coords = df[['POZO', 'LOCACION', 'ESTE', 'NORTE']].copy()
    
    # Agregamos Lat/Lon para el mapa (asumiendo que las columnas existen o las calculamos)
    # Si tu archivo ya tiene Latitud y Longitud, cámbialas aquí:
    if 'LATITUD' in df.columns:
        df_coords['lat_dec'] = df['LATITUD'].apply(dms_to_decimal)
        df_coords['lon_dec'] = df['LONGITUD'].apply(dms_to_decimal)
    else:
        # Si no hay Lat/Lon, podemos usar una aproximación o avisar
        # Para este ejemplo, intentaremos leerlas si están en las columnas 7 y 8
        try:
            df_coords['lat_dec'] = df.iloc[:, 7].apply(dms_to_decimal)
            df_coords['lon_dec'] = df.iloc[:, 8].apply(dms_to_decimal)
        except:
            st.warning("No se encontraron columnas de Latitud/Longitud para el mapa.")
    
    # Agrupamos por Locación (Cluster)
    df_final = df_coords.dropna(subset=['lat_dec', 'lon_dec']).groupby('LOCACION').agg({
        'lat_dec': 'first', 
        'lon_dec': 'first', 
        'ESTE': 'first',
        'NORTE': 'first',
        'POZO': lambda x: ', '.join(x.astype(str))
    }).reset_index()
    
    return df_final

# --- INTERFAZ ---
st.title("🚜 Plan de Movilización: Rubiales - Caño Sur Este")

try:
    # Carga del archivo limpio
    df_maestro = cargar_base_coordenadas("COORDENADAS_RUB_CASE.csv")

    st.sidebar.header("Ruta de Equipos")
    ruta_input = st.sidebar.text_area("Lista de Locaciones (Ej: CASE0015):", placeholder="CASE0015\nAGRIO-1")
    nombres_ruta = [n.strip().upper() for n in re.split(r'[\n,]+', ruta_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres_ruta):
        match = df_maestro[df_maestro['LOCACION'].str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'orden': i + 1,
                'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 
                'lon': match.iloc[0]['lon_dec'], 
                'pozos': match.iloc[0]['POZO'],
                'este': match.iloc[0]['ESTE']
            })

    # Mapa base
    m = folium.Map(location=[df_maestro['lat_dec'].mean(), df_maestro['lon_dec'].mean()], zoom_start=11)

    for p in puntos_ruta:
        folium.Marker(
            location=[p['lat'], p['lon']],
            popup=f"Locación: {p['nombre']}<br>Pozos: {p['pozos']}<br>Este: {p['este']}",
            icon=folium.Icon(color='black', icon='oil-well', prefix='fa')
        ).add_to(m)

        folium.map.Marker(
            [p['lat'], p['lon']],
            icon=DivIcon(
                html=f'<div style="font-size: 11pt; color: white; background-color: black; border-radius: 50%; width: 25px; height: 25px; display: flex; justify-content: center; align-items: center; border: 2px solid white; font-weight: bold;">{p["orden"]}</div>',
            )
        ).add_to(m)

    st_folium(m, width=1100, height=600)

except Exception as e:
    st.error(f"Error: {e}")
