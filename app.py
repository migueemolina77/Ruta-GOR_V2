import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
import requests
from folium.features import DivIcon

# Configuración de página
st.set_page_config(page_title="Logística Rubiales & CASE - Etapa 2", layout="wide")

# 1. Carga del archivo (Formato limpio: GERENCIA, LOCACION, ESTE, NORTE, POZO)
@st.cache_data
def cargar_base_coordenadas(file_path):
    # Leemos el CSV directamente (sin saltar filas)
    df = pd.read_csv(file_path, encoding='latin-1')
    
    # Limpiamos nombres de columnas por si tienen espacios invisibles
    df.columns = df.columns.str.strip()
    
    # Para el mapa, necesitamos Latitud y Longitud. 
    # Como este archivo tiene ESTE y NORTE (Planas), el código intentará 
    # usar las columnas de posición 7 y 8 si existen para el mapa.
    def extraer_valor(row, pos):
        try: return row.iloc[pos]
        except: return None

    # Creamos el dataframe de trabajo
    df_coords = pd.DataFrame()
    df_coords['pozo'] = df['POZO']
    df_coords['cluster'] = df['LOCACION']
    df_coords['este'] = df['ESTE']
    df_coords['norte'] = df['NORTE']
    
    # Intentamos capturar Lat/Lon de las columnas ocultas para Folium
    # En tu archivo CSV, parecen ser las columnas 7 y 8 (si se exportaron)
    try:
        df_coords['lat_dec'] = df.iloc[:, 7] 
        df_coords['lon_dec'] = df.iloc[:, 8]
    except:
        # Si no existen, el mapa no se mostrará, pero la tabla sí.
        df_coords['lat_dec'] = None
        df_coords['lon_dec'] = None
    
    # Agrupamos por Locación
    df_final = df_coords.groupby('cluster').agg({
        'lat_dec': 'first',
        'lon_dec': 'first',
        'este': 'first',
        'norte': 'first',
        'pozo': lambda x: ', '.join(x.astype(str))
    }).reset_index()
    
    return df_final

# --- INTERFAZ ---
st.title("🚜 Plan de Movilización: Rubiales - Caño Sur Este")

try:
    # Usamos el nombre exacto del archivo cargado
    df_maestro = cargar_base_coordenadas("COORDENADAS_RUB_CASE.csv")

    st.sidebar.header("Ruta de Movilización")
    ruta_input = st.sidebar.text_area("Pega las Locaciones:", placeholder="CASE0015\nAGRIO-1")
    nombres_ruta = [n.strip().upper() for n in re.split(r'[\n,]+', ruta_input) if n.strip()]

    puntos_ruta = []
    for i, nombre in enumerate(nombres_ruta):
        match = df_maestro[df_maestro['cluster'].astype(str).str.upper() == nombre]
        if not match.empty:
            puntos_ruta.append({
                'orden': i + 1,
                'nombre': nombre, 
                'lat': match.iloc[0]['lat_dec'], 
                'lon': match.iloc[0]['lon_dec'], 
                'pozos': match.iloc[0]['pozo'],
                'este': match.iloc[0]['este']
            })

    # Si hay coordenadas GPS, mostramos el mapa
    if not df_maestro['lat_dec'].isnull().all():
        m = folium.Map(location=[df_maestro['lat_dec'].dropna().mean(), 
                                 df_maestro['lon_dec'].dropna().mean()], zoom_start=11)
        
        for p in puntos_ruta:
            if pd.notnull(p['lat']):
                folium.Marker(
                    location=[p['lat'], p['lon']],
                    popup=f"Locación: {p['nombre']}\nEste: {p['este']}",
                    icon=folium.Icon(color='orange', icon='info-sign')
                ).add_to(m)
        
        st_folium(m, width=1100, height=600)
    else:
        st.warning("El archivo no contiene columnas de Latitud/Longitud. Mostrando solo tabla de datos.")
        
    # Siempre mostramos la tabla de los puntos seleccionados
    if puntos_ruta:
        st.write("### Resumen de Coordenadas de la Ruta")
        st.table(pd.DataFrame(puntos_ruta)[['orden', 'nombre', 'este', 'pozos']])

except Exception as e:
    st.error(f"Error al leer el archivo: {e}")
