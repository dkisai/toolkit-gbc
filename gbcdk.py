import configparser
import csv
import os
import pandas as pd
import requests
import yaml
from bs4 import BeautifulSoup as bs
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from sqlalchemy import create_engine
from tqdm import tqdm
from yaml.loader import SafeLoader

class GbconnectedDk:
    """
    Clase para agilizar el trabajo de soporte N2 en Gbconnected.
    """

    
    def __init__(self):
        """
        Inicializa la instancia leyendo la configuración desde un archivo 'config.ini'.
        """
        self._config = configparser.ConfigParser()
        self._config.read('config.ini')

    
    def _create_doc(self):
        """
        Crea un archivo CSV con cabeceras para almacenar información sobre las plantas.
        """
        header = ['version', 'planta', 'ip']
        with open(str(date.today()) + '.csv', 'w', newline='') as file:
            csv_writer = csv.writer(file)
            csv_writer.writerow(header)
            file.close()
        
    
    def _write_data(self, text):
        """
        Agrega una línea de texto al archivo CSV del día actual.

        Args:
            text (List[str]): Texto para escribir en el archivo.
        """
        with open(str(date.today()) + '.csv', 'a', newline='') as write_obj:
            csv_writer2 = csv.writer(write_obj)
            csv_writer2.writerow(text)
        
        
    def _prepare_session(self, ip):
        """
        Prepara una sesión HTTP para interactuar con la planta.

        Args:
            ip (str): Dirección IP de la planta.

        Returns:
            Tuple[Session, str]: La sesión HTTP preparada y la URL base.
        """
        user = self._config.get('sc', 'user')
        passwd = self._config.get('sc', 'passwd')
        url = f'http://{ip}:8080/gbconnected/'
        s = requests.session()
        csrf_token = s.get(url).cookies['XSRF-TOKEN']
        login_payload = {
            '_csrf': csrf_token,
            'username': user,
            'password': passwd
        }
        s.post(f'{url}login', data=login_payload)
        return s, url


    def _get_version(self, ip):
        """
        Obtiene la versión de la planta y la escribe en el archivo CSV.

        Args:
            ip (str): Dirección IP de la planta.
        """
        try:
            s, url = self._prepare_session(ip[0])
            soup = bs(s.get(f'{url}private/configuracionfabrica').text, 'html.parser')
            data = soup.find_all('b')
            planta = str(data[1])
            version = str(data[2])
            text = [version[38:-5], planta[11:-5], ip[0]]
            self._write_data(text)
        except Exception:
            text = 'ERROR', ip[1], ip[0]
            self._write_data(text)
        
        
    def erase_cache(self, ip):
        """
        Borra la caché de la planta.

        Args:
            ip (str): Dirección IP de la planta.
        """        
        s, url = self._prepare_session(ip)
        s.get(f'{url}actuator/eliminacioncache').text
        print('Borrado de cache listo')
    

    def _read_yaml_file(self, file_path):
        """
        Lee un archivo YAML y devuelve una lista de todas las direcciones IP.

        Args:
            file_path (str): Ruta al archivo YAML.

        Returns:
            List[str]: Lista de todas las direcciones IP.
        """        
        with open(file_path, 'r') as yaml_file:
            yaml_content = yaml.load(yaml_file, Loader=SafeLoader)
        all_data = []
        for ip in yaml_content.values():
            all_data += ip
        return all_data


    def version_check(self):
        """
        Verifica la versión de todas las plantas listadas en el archivo 'plantas2.yaml'.
        """
        self._create_doc()
        all_data = self._read_yaml_file("plantas.yaml")        
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(tqdm(executor.map(self._get_version, all_data),
                                desc= 'Procesando',
                                total=len(all_data),
                                ncols = 100))
        print('Archivo generado')


    def _get_query_local(self, planta, query):
        """
        Ejecuta una consulta SQL en una planta y guarda los resultados en un archivo CSV.

        Args:
            planta (str): Nombre de la planta.
            query (str): Consulta SQL a ejecutar.
        """
        user = self._config.get('mysql', 'user')
        user_win = self._config.get('mysql', 'user_win')
        password = self._config.get('mysql', 'password')
        password_win = self._config.get('mysql', 'password_win')
        port = self._config.get('mysql', 'port')
        database = self._config.get('mysql', 'database')
        host = planta[0]
        engine = create_engine(f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}")
        engine_win = create_engine(f"mysql+mysqlconnector://{user_win}:{password_win}@{host}:{port}/{database}")
        try:
            result_df = pd.read_sql(query, con=engine)
            result_df.to_csv(f'Local/{planta[1]}.csv', index=False, encoding='utf-8')
        except Exception as e:
            print(e)
            result_df_win = pd.read_sql(query, con=engine_win)
            result_df_win.to_csv(f'Local/{planta[1]}.csv', index=False, encoding='utf-8')


    def query_local(self, query):
        """
        Ejecuta una consulta SQL en todas las plantas listadas en el archivo 'plantas.yaml'.

        Args:
            query (str): Consulta SQL a ejecutar.
        """
        all_data = self._read_yaml_file("plantas.yaml")
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(tqdm(executor.map(self._get_query_local, all_data, [query] * len(all_data)),
                                desc='Procesando',
                                total=len(all_data),
                                ncols=100))
        print('Archivo generado')


    def _get_query_rds(self, planta, query):
        """
        Ejecuta una consulta SQL en una base de datos remota y guarda los resultados en un archivo CSV.

        Args:
            planta (str): Nombre de la planta.
            query (str): Consulta SQL a ejecutar.
        """
        host = self._config.get('rds', 'host')
        port = self._config.get('rds', 'port')
        dbname = self._config.get('rds', 'dbname')
        user = self._config.get('rds', 'user')
        password = self._config.get('rds', 'password')
        engine = create_engine(f"postgresql://{user}:{password}@{host}:{port}/{dbname}")
        try:
            schema = f"SET search_path TO {planta};"
            result_df = pd.read_sql(schema+query, con=engine)
            result_df.to_csv(f'Historico/{planta}.csv', index=False, encoding='utf-8')
        except Exception as e:
            data = {'Column1': ['ERROR'],
                    'Column2': [e]}
            df = pd.DataFrame(data)
            df.to_csv(f'Historico/error_{planta}.csv', index=False, encoding='utf-8')


    def query_rds(self, query):
        """
        Ejecuta una consulta SQL en una base en rds remota para todas las plantas en el archivo 'rds_plantas.yaml'.

        Args:            
        query (str): Consulta SQL a ejecutar.
        """
        all_data = self._read_yaml_file("rds_plantas.yaml")
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(tqdm(executor.map(self._get_query_rds, all_data, [query] * len(all_data)),
                                desc= 'Procesando',
                                total=len(all_data),
                                ncols = 100))
        print('Archivo generado')
        

    def combinar_csv(self, directorio):
        """
        Combina los archivos csv del directorio especificado en uno, generando una columna nueva
        con el nombre del archivo
        
        Args:
        directorio(str): Directorio donde estan los archivos a combinar
        """
        # Lista para almacenar los dataframes
        dataframes = []

        # Recorre todos los archivos en el directorio
        for nombre_archivo in os.listdir(directorio):
            # Verifica si el archivo es un csv
            if nombre_archivo.endswith('.csv'):
                # Crea la ruta completa al archivo
                ruta_archivo = os.path.join(directorio, nombre_archivo)
                # Lee el archivo csv en un dataframe
                df = pd.read_csv(ruta_archivo)
                # Agrega una nueva columna con el nombre del archivo (sin la extensión)
                df['archivo'] = os.path.splitext(nombre_archivo)[0]
                df = df[['archivo'] + [col for col in df.columns if col != 'archivo']]
                # Agrega el dataframe a la lista
                dataframes.append(df)

        # Combina todos los dataframes en uno solo
        combined_df = pd.concat(dataframes, axis=0, ignore_index=True)
        combined_df.to_csv(f"Archivo_{directorio}_combinado.csv", index=False)
        print('Archivo generado')
