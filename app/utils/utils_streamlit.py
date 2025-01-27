import streamlit as st
import folium
import pandas as pd
import os
from utils.lat_long import get_all_states, get_state, get_geocoding
from utils.utils_transformations import TiposImoveis, get_columns_intersection
from folium.plugins import GroupedLayerControl
import asyncio
from utils.utils_scraper import ScraperArgenProp, ScraperZonaProp
import smtplib
import email.message
import re
import time
import textwrap
from dotenv import load_dotenv
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
import openpyxl
from utils.utils_storage import ParquetStorage, DuckDBStorage, get_paths
from utils.log_config import get_logger

# Carregando variáveis de ambiente
load_dotenv()

# Criando logger
logger = get_logger()

def get_widgets():
    '''
        Retorna os widgets da página do streamlit
    '''
    
    # WIDGETS
    # locais = list(get_all_states().keys())
    # locais.sort()
    locais = [x.replace(' ', '-') for x in list(get_all_states().keys())]
    locais.extend(['buenos-aires', 'mendoza'])
    locais.sort()

    with st.expander('### Principais Filtros'):
        # with st.container(height = 120, border=True):
        col1_r1, col2_r1, col3_r1, col4_r1, col5_r1 = st.columns(5)
        col1_r2, col2_r2, col3_r2, col4_r2, col5_r2 = st.columns(5)
        
        col1_r1.multiselect(
            label = 'Base de Busca',
            options = ['Argenprop','Zonaprop'],
            key = 'base_busca'
        )

        col2_r1.multiselect(
            label = 'Locais',
            options = locais,
            key = 'locais'
        )

        col3_r1.multiselect(
            label = 'Tipos de Imóveis',
            options = TiposImoveis().total_tipos(),
            key = 'tipos'
        )

        col4_r1.multiselect(
            'Moeda do Aluguel',
            options = ['USD', '$', 'Sem info'],
            key = 'aluguel_moeda'
        )

        col1_r2.slider(
            'Aluguel',
            min_value = 0,
            max_value = 999_999,
            value = (0, 999_999),
            step = 1000,
            key = 'aluguel_valor'
        )

        col5_r1.multiselect(
            'Moeda das Expensas',
            options = ['USD', '$', 'Sem info'],
            key = 'expensas_moeda'
        )

        col2_r2.slider(
            'Expensas',
            min_value = 0,
            max_value = 999_999,
            value = (0, 999_999),
            step = 1000,
            key = 'expensas_valor'
        )

        col3_r2.slider(
            'Ambientes',
            min_value = 0,
            max_value = 100,
            value = (0, 100),
            key = 'ambientes'
        )

        col4_r2.slider(
            'Dormitórios',
            min_value = 0,
            max_value = 100,
            value = (0, 100),
            key = 'dormitorios'
        )

        col5_r2.slider(
            'Distância para UNR (km)',
            min_value = 0.0,
            max_value = 60.0,
            value = (0.0, 100.0),
            key = 'distancia_unr'
        )

    st.sidebar.markdown('### Outros Filtros')

    st.sidebar.slider(
        'Área Útil (m2)',
        min_value = 0.0,
        max_value = 999.0,
        value = (0.0, 999.0),
        key = 'area_util'
    )

    st.sidebar.slider(
        'Banheiros',
        min_value = 0,
        max_value = 100,
        value = (0, 100),
        key = 'banheiros'
    )
    
    st.sidebar.slider(
        'Distância para Hospital Provincial (km)',
        min_value = 0.0,
        max_value = 60.0,
        value = (0.0, 100.0),
        key = 'distancia_provincial'
    )

    st.sidebar.slider(
        'Distância para Hospital de Niños (km)',
        min_value = 0.0,
        max_value = 60.0,
        value = (0.0, 100.0),
        key = 'distancia_ninos'
    )

    st.sidebar.slider(
        'Distância para Hospital Carrasco (km)',
        min_value = 0.0,
        max_value = 60.0,
        value = (0.0, 100.0),
        key = 'distancia_carrasco'
    )

    st.sidebar.slider(
        'Distância para Hospital Baigorria (km)',
        min_value = 0.0,
        max_value = 60.0,
        value = (0.0, 100.0),
        key = 'distancia_baigorria'
    )

def get_email_widgets():
    '''
        Retorna os widgets relativos ao envio de emails com dados dos imóveis selecionados
    '''

    st.text_input(
        label = 'E-mails (separados por vírgula)',
        key = 'email_usuario',
         help = 'E-mail para enviar os imóveis selecionados.'
    )

    e1, e2 = st.columns(2)
    e1.button(
        label = '## Limpar Lista de Ids',
        key = 'limpar',
        type = 'primary',
        use_container_width = True,
        help = "Ao clicar em um imóvel, este é incluido em uma lista de interesse. Para reiniciar a lista, basta clicar no botão."
    )
    

    e2.button(
        label = 'Enviar E-mail',
        key = 'enviar_email',
        type = 'primary',
        use_container_width = True,
        help = '(WIP) Envia a lista de imóveis selecionados para o e-mail passado.'
    )

def get_map(df: pd.DataFrame, tipo_layer: str = 'bairro'):
    '''
        Cria um mapa com base no dataframe passado

        Parâmetros:
        ----------
        df: pd.DataFrame
            dataframe com dados geográficos
        tipo_layer: 'bairro' ou 'base'
            define qual layer será definido no mapa
            impossibilidade de colocar um mesmo marker em layers diferentes
    '''

    # Localização inicial do mapa
    x = get_geocoding(endereco = 'centro', cidade = st.session_state.locais[0], estado = get_state(cidade = st.session_state.locais[0]))
    lat_long = [x['lat'], x['lng']]

    # Inicializando o mapa
    m = folium.Map(
        location = lat_long, #[-32.945, -60.667],
        zoom_start = 15
    )

    # Criando grupos de layers para filtrar, dentro do mapa, a base
    zonaprop_group = folium.FeatureGroup("Zonaprop")
    argenprop_group = folium.FeatureGroup("Argenprop")

    # Layers dos bairros. cria uma layer pra cada bairro distinto
    dict_bairros = {}

    for i in df.bairro.sort_values().unique():
        dict_bairros[i] = folium.FeatureGroup(i)

    for _, row in df.iterrows():
        # Definindo o ícone
        zona_icon = [
            folium.features.CustomIcon(os.path.join(os.getcwd(), 'assets', 'argenprop.jpg') if os.getcwd().__contains__('app') else os.path.join(os.getcwd(), 'app', 'assets', 'argenprop.jpg'), icon_size=(22, 26))
            if row['base'] == 'argenprop'
            else folium.features.CustomIcon(os.path.join(os.getcwd(), 'assets', 'zonaprop.png') if os.getcwd().__contains__('app') else os.path.join(os.getcwd(), 'app', 'assets', 'zonaprop.png'), icon_size=(22, 26))
        ][0]
        
        # Criando marker
        marker = folium.Marker(
            location = [row.latitude, row.longitude],
            popup = f'''
                <b>Id</b>: {row['id']} <br>
                <b>Base</b>: {row['base']} <br> 
                <b>Endereço</b>:  {row['endereco']} <br> 
                <b>Imobiliária</b>:  {row['imobiliaria']} <br> 
                <b>Área Útil</b>:  {row['area_util']} <br> 
                <b>Dormitórios</b>:  {row['dormitorios']} <br> 
                <b>Ambientes</b>:  {row['ambientes']} <br> 
                <b>Banheiros</b>:  {row['banheiros']} <br> 
                <b>Link</b>:  <a href={row['url']}>{row['url']}</a> <br> 
            ''',
            # hoover
            tooltip = f'''
                <b>Tipo de Imóvel</b>: {row['tipo_imovel']} <br>
                <b>Bairro</b>: {row['bairro']} <br> 
                <b>Aluguel ({row.aluguel_moeda})</b>: {row['aluguel_valor']} <br> 
                <b>Expensas ({row.expensas_moeda})</b>: {row['expensas_valor']} <br> 
                <b>Valor Total ({row.aluguel_moeda})</b>: {row.valor_total_aluguel}
            ''',
            icon = zona_icon
        )

        if tipo_layer == 'bairro':
            marker.add_to(dict_bairros[row['bairro']])
        else:
            if row['base'] == 'argenprop':
                marker.add_to(argenprop_group)
            else:
                marker.add_to(zonaprop_group)
    
    if tipo_layer == 'bairro':
        for i in dict_bairros:
            m.add_child(dict_bairros[i])
        
        GroupedLayerControl(
            groups = {'Bairros': [dict_bairros[i] for i in dict_bairros]},
            collapsed = True,
            exclusive_groups = False
        ).add_to(m)
    else:
        m.add_child(zonaprop_group)
        m.add_child(argenprop_group)
    
        GroupedLayerControl(
            groups = {'Base de Busca': [zonaprop_group, argenprop_group]},
            collapsed = True,
            exclusive_groups=False
        ).add_to(m)

    return m

def get_zonaprop_duckdb():
    
    logger.info('Limpando dados da base Zonaprop')

    try:
        # Limpando dados anteriores a hoje
        for tabela in ['paginas_zonaprop', 'bronze_imoveis_zonaprop', 'silver_imoveis_zonaprop']:
            DuckDBStorage(_base = 'zonaprop', _folder = 'imoveis', _tabela = tabela).drop_old_data(timedelta = 1)
        
        # Checando se os dados solicitados já existem na base
        check_silver = DuckDBStorage(_base = 'zonaprop', _folder = 'imoveis', _tabela = 'silver_imoveis_zonaprop', _tipos = st.session_state.tipos, _locais = st.session_state.locais).check_table()

        # Retornando dados
        if check_silver == []:
            logger.info('Rodando scraper Zonaprop para todos os tipos passados')
            return DuckDBStorage(_base = 'zonaprop', _folder = 'imoveis', _tabela = 'silver_imoveis_zonaprop', _tipos = st.session_state.tipos, _locais = st.session_state.locais).query_data()
        
        else:
            logger.info(f'Rodando scraper Zonaprop apenas para {check_silver}')
            df = ScraperZonaProp(_tipo = check_silver, _local = st.session_state.locais).get_final_dataframe()
            return DuckDBStorage(_base = 'zonaprop', _folder = 'imoveis', _tabela = 'silver_imoveis_zonaprop', _tipos = st.session_state.tipos, _locais = st.session_state.locais).query_data()
    except:
        # df = pd.DataFrame(
        #     columns = [
        #         'id', 'base', 'tipo_imovel', 'estado', 'cidade', 'bairro', 'endereco', 'url', 'descricao', 'titulo', 'aluguel_moeda', 'aluguel_valor',
        #         'desconto_aluguel', 'expensas_moeda', 'expensas_valor', 'valor_total_aluguel', 'area_total', 'area_util', 'ambientes',
        #         'dormitorios', 'banheiros', 'garagens', 'destaque', 'imobiliaria', 'data', 'ano', 'mes', 'dia', 'latitude', 'longitude', 'coordenadas',
        #         'distancia_unr', 'distancia_hospital_provincial', 'distancia_hospital_baigorria', 'distancia_hospital_ninos', 'distancia_hospital_carrasco'
        #     ]
        # )
        df = DuckDBStorage(_base = 'zonaprop', _folder = 'imoveis', _tabela = 'silver_imoveis_zonaprop', _tipos = st.session_state.tipos, _locais = st.session_state.locais).query_data()

        return df

def get_argenprop_duckdb():   
    
    logger.info('Limpando dados da base Argenprop')

    try:
        # Limpando dados anteriores a hoje
        for tabela in ['paginas_argenprop', 'bronze_imoveis_argenprop', 'silver_imoveis_argenprop']:
            DuckDBStorage(_base = 'argenprop', _folder = 'imoveis', _tabela = tabela).drop_old_data(timedelta = 1)
        
        # Checando se os dados solicitados já existem na base
        check_silver = DuckDBStorage(_base = 'argenprop', _folder = 'imoveis', _tabela = 'silver_imoveis_argenprop', _tipos = st.session_state.tipos, _locais = st.session_state.locais).check_table()

        # Retornando dados
        if check_silver != []:
            logger.info(f'Rodando scraper Zonaprop apenas para {check_silver}')
            df_argenprop = asyncio.run(ScraperArgenProp(_tipo = check_silver, _local = st.session_state.locais).get_final_dataframe())
            return DuckDBStorage(_base = 'argenprop', _folder = 'imoveis', _tabela = 'silver_imoveis_argenprop', _tipos = st.session_state.tipos, _locais = st.session_state.locais).query_data()
        
        else:
            logger.info('Rodando scraper Argenprop para todos os tipos passados')
            return DuckDBStorage(_base = 'argenprop', _folder = 'imoveis', _tabela = 'silver_imoveis_argenprop', _tipos = st.session_state.tipos, _locais = st.session_state.locais).query_data()
    except:
        # df = pd.DataFrame(
        #     columns = [
        #         'id', 'base', 'tipo_imovel', 'estado', 'cidade', 'bairro', 'endereco', 'url', 'descricao', 'titulo', 'aluguel_moeda', 'aluguel_valor',
        #         'expensas_moeda', 'expensas_valor', 'valor_total_aluguel', 'area_util', 'antiguidade', 'banheiros', 'tipo_banheiro', 'ambientes', 'dormitorios',
        #         'orientacao', 'garagens', 'estado_propriedade', 'tipo_local', 'imobiliaria', 'num_fotos', 'fotos', 'card_points', 'wsp', 'data',
        #         'ano', 'mes', 'dia', 'latitude', 'longitude', 'coordenadas', 'distancia_unr', 'distancia_hospital_provincial',
        #         'distancia_hospital_baigorria', 'distancia_hospital_ninos', 'distancia_hospital_carrasco']
        # )
        df = DuckDBStorage(_base = 'argenprop', _folder = 'imoveis', _tabela = 'silver_imoveis_argenprop', _tipos = st.session_state.tipos, _locais = st.session_state.locais).query_data()

        return df

def get_zonaprop_parquet():
    pass
    # # Paths
    # path_page_zonaprop = get_paths()['zonaprop']['paginas']
    # bronze_zonaprop = get_paths()['zonaprop']['bronze']
    # silver_zonaprop = get_paths()['zonaprop']['silver']

    # # Checando se os dados do dia atual existem
    # ParquetStorage(_path = path_page_zonaprop, _locais = st.session_state.locais).check_parquet()
    # ParquetStorage(_path = bronze_zonaprop, _locais = st.session_state.locais).check_parquet()
    # ParquetStorage(_path = silver_zonaprop, _locais = st.session_state.locais).check_parquet()

    # # Checando se existem arquivos
    # check_page_zonaprop = ParquetStorage(_path = path_page_zonaprop, _locais = st.session_state.locais).check_files()
    # check_bronze_zonaprop = ParquetStorage(_path = bronze_zonaprop, _locais = st.session_state.locais).check_files()

    # # Caso não exista arquivo na página bronze, carrega tudo
    # if check_bronze_zonaprop == 0:
    #     df_zonaprop = ScraperZonaProp(
    #             _tipo = [
    #                 'casas','departamentos','ph','locales-comerciales','oficinas-comerciales','bodegas-galpones','cocheras','depositos','terrenos',
    #                 'edificios','quintas-vacacionales','campos','fondos-de-comercio','hoteles', 'consultorios','cama-nautica','bovedas-nichos-y-parcelas'
    #             ], 
    #             _local = st.session_state.locais
    #         ).get_final_dataframe()

    #     df_zonaprop.loc[df_zonaprop.tipo_imovel.isin(st.session_state.tipos)]

    # else:
    #     df_zonaprop = pd.read_parquet(
    #             path = silver_zonaprop,
    #             filters = [
    #                 ('cidade', 'in', st.session_state.locais),
    #                 ('tipo_imovel', 'in', st.session_state.tipos)
    #             ]
    #         )
    
    # return df_zonaprop
    
def get_argenprop_parquet():
    pass
    # # Paths
    # path_page_argenprop = get_paths()['argenprop']['paginas']
    # bronze_argenprop = get_paths()['argenprop']['bronze']
    # silver_argenprop = get_paths()['argenprop']['silver']

    # # Checando se os dados do dia atual existem
    # ParquetStorage(_path = path_page_argenprop, _locais = st.session_state.locais).check_parquet()
    # ParquetStorage(_path = bronze_argenprop, _locais = st.session_state.locais).check_parquet()
    # ParquetStorage(_path = silver_argenprop, _locais = st.session_state.locais).check_parquet()

    # # Checando se existem arquivos
    # check_page_argenprop = ParquetStorage(_path = path_page_argenprop, _locais = st.session_state.locais).check_files()
    # check_bronze_argenprop = ParquetStorage(_path = bronze_argenprop, _locais = st.session_state.locais).check_files()

    # # Caso não exista arquivo na página bronze, carrega tudo
    # if check_bronze_argenprop == 0:
    #     df_argenprop = asyncio.run(
    #         ScraperArgenProp(
    #             _tipo = ['departamentos','casas','campos','cocheras','fondos-de-comercio','galpones','hoteles','locales','negocios-especiales','oficinas','ph','quintas','terrenos'], 
    #             _local = st.session_state.locais
    #         ).get_final_dataframe()
    #     )

    #     df_argenprop.loc[df_argenprop.tipo_imovel.isin(st.session_state.tipos)]

    # else:
    #     df_argenprop = pd.read_parquet(
    #             path = silver_argenprop,
    #             filters = [
    #                 ('cidade', 'in', st.session_state.locais),
    #                 ('tipo_imovel', 'in', st.session_state.tipos)
    #             ]
    #         )
    
    # return df_argenprop

def get_dataframe(df_argenprop: pd.DataFrame = None, df_zonaprop: pd.DataFrame = None):

    # DADOS
    if ('Argenprop' in st.session_state.base_busca) and ('Zonaprop' in st.session_state.base_busca):
        logger.info('Obtendo dados do Argenprop')
        df_argenprop = get_argenprop_duckdb()

        time.sleep(5)
        
        logger.info('Obtendo dados do Zonaprop')
        df_zonaprop = get_zonaprop_duckdb()

        if 'rosario' in st.session_state.locais:
            df_final = (
                pd.concat(
                    [
                        df_argenprop.loc[:, get_columns_intersection(df_argenprop, df_zonaprop)],
                        df_zonaprop.loc[:, get_columns_intersection(df_argenprop, df_zonaprop)]
                    ],
                    ignore_index = True
                )
                .pipe(
                    lambda df: df.loc[
                        (df.distancia_unr.between(st.session_state.distancia_unr[0], st.session_state.distancia_unr[1]))
                        & (df.distancia_hospital_provincial.between(st.session_state.distancia_provincial[0], st.session_state.distancia_provincial[1]))
                        & (df.distancia_hospital_ninos.between(st.session_state.distancia_ninos[0], st.session_state.distancia_ninos[1]))
                        & (df.distancia_hospital_carrasco.between(st.session_state.distancia_carrasco[0], st.session_state.distancia_carrasco[1]))
                        & (df.distancia_hospital_baigorria.between(st.session_state.distancia_baigorria[0], st.session_state.distancia_baigorria[1]))
                        & (df.area_util.between(st.session_state.area_util[0], st.session_state.area_util[1]))
                        & (df.banheiros.between(st.session_state.banheiros[0], st.session_state.banheiros[1]))
                        & (df.ambientes.between(st.session_state.ambientes[0], st.session_state.ambientes[1]))
                        & (df.dormitorios.between(st.session_state.dormitorios[0], st.session_state.dormitorios[1]))
                        & (df.aluguel_valor.between(st.session_state.aluguel_valor[0], st.session_state.aluguel_valor[1]))
                        & (df.expensas_valor.between(st.session_state.expensas_valor[0], st.session_state.expensas_valor[1]))
                        & (df.aluguel_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.aluguel_moeda) == 0 else st.session_state.aluguel_moeda
                            )
                        )
                        & (df.expensas_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.expensas_moeda) == 0 else st.session_state.expensas_moeda
                            )
                        )
                    ]
                )
                .reset_index(drop = True)
            )
        else:
            df_final = (
                pd.concat(
                    [
                        df_argenprop.loc[:, get_columns_intersection(df_argenprop, df_zonaprop)],
                        df_zonaprop.loc[:, get_columns_intersection(df_argenprop, df_zonaprop)]
                    ],
                    ignore_index = True
                )
                .pipe(
                    lambda df: df.loc[
                        (df.area_util.between(st.session_state.area_util[0], st.session_state.area_util[1]))
                        & (df.banheiros.between(st.session_state.banheiros[0], st.session_state.banheiros[1]))
                        & (df.ambientes.between(st.session_state.ambientes[0], st.session_state.ambientes[1]))
                        & (df.dormitorios.between(st.session_state.dormitorios[0], st.session_state.dormitorios[1]))
                        & (df.aluguel_valor.between(st.session_state.aluguel_valor[0], st.session_state.aluguel_valor[1]))
                        & (df.expensas_valor.between(st.session_state.expensas_valor[0], st.session_state.expensas_valor[1]))
                        & (df.aluguel_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.aluguel_moeda) == 0 else st.session_state.aluguel_moeda
                            )
                        )
                        & (df.expensas_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.expensas_moeda) == 0 else st.session_state.expensas_moeda
                            )
                        )
                    ]
                )
                .reset_index(drop = True)
            )

    elif 'Argenprop' in st.session_state.base_busca:
        logger.info(f'Obtendo apenas dados do {st.session_state.base_busca} para o local {st.session_state.locais}, tipos {st.session_state.tipos}')
        df_argenprop = get_argenprop_duckdb()
        
        if 'rosario' in st.session_state.locais:
            df_final = (
                df_argenprop
                .pipe(
                    lambda df: df.loc[
                        (df.distancia_unr.between(st.session_state.distancia_unr[0], st.session_state.distancia_unr[1]))
                        & (df.distancia_hospital_provincial.between(st.session_state.distancia_provincial[0], st.session_state.distancia_provincial[1]))
                        & (df.distancia_hospital_ninos.between(st.session_state.distancia_ninos[0], st.session_state.distancia_ninos[1]))
                        & (df.distancia_hospital_carrasco.between(st.session_state.distancia_carrasco[0], st.session_state.distancia_carrasco[1]))
                        & (df.distancia_hospital_baigorria.between(st.session_state.distancia_baigorria[0], st.session_state.distancia_baigorria[1]))
                        & (df.area_util.between(st.session_state.area_util[0], st.session_state.area_util[1]))
                        & (df.banheiros.between(st.session_state.banheiros[0], st.session_state.banheiros[1]))
                        & (df.ambientes.between(st.session_state.ambientes[0], st.session_state.ambientes[1]))
                        & (df.dormitorios.between(st.session_state.dormitorios[0], st.session_state.dormitorios[1]))
                        & (df.aluguel_valor.between(st.session_state.aluguel_valor[0], st.session_state.aluguel_valor[1]))
                        & (df.expensas_valor.between(st.session_state.expensas_valor[0], st.session_state.expensas_valor[1]))
                        & (df.aluguel_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.aluguel_moeda) == 0 else st.session_state.aluguel_moeda
                            )
                        )
                        & (df.expensas_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.expensas_moeda) == 0 else st.session_state.expensas_moeda
                            )
                        )
                    ]
                )
                .reset_index(drop = True)
            )
        else:
            df_final = (
                df_argenprop
                .pipe(
                    lambda df: df.loc[
                        (df.area_util.between(st.session_state.area_util[0], st.session_state.area_util[1]))
                        & (df.banheiros.between(st.session_state.banheiros[0], st.session_state.banheiros[1]))
                        & (df.ambientes.between(st.session_state.ambientes[0], st.session_state.ambientes[1]))
                        & (df.dormitorios.between(st.session_state.dormitorios[0], st.session_state.dormitorios[1]))
                        & (df.aluguel_valor.between(st.session_state.aluguel_valor[0], st.session_state.aluguel_valor[1]))
                        & (df.expensas_valor.between(st.session_state.expensas_valor[0], st.session_state.expensas_valor[1]))
                        & (df.aluguel_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.aluguel_moeda) == 0 else st.session_state.aluguel_moeda
                            )
                        )
                        & (df.expensas_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.expensas_moeda) == 0 else st.session_state.expensas_moeda
                            )
                        )
                    ]
                )
                .reset_index(drop = True)
            )

    elif 'Zonaprop' in st.session_state.base_busca:
        logger.info(f'Obtendo apenas dados do {st.session_state.base_busca} para o local {st.session_state.locais}, tipos {st.session_state.tipos}')
        df_zonaprop = get_zonaprop_duckdb()
        
        if 'rosario' in st.session_state.locais:
            df_final = (
                df_zonaprop
                .pipe(
                    lambda df: df.loc[
                        (df.distancia_unr.between(st.session_state.distancia_unr[0], st.session_state.distancia_unr[1]))
                        & (df.distancia_hospital_provincial.between(st.session_state.distancia_provincial[0], st.session_state.distancia_provincial[1]))
                        & (df.distancia_hospital_ninos.between(st.session_state.distancia_ninos[0], st.session_state.distancia_ninos[1]))
                        & (df.distancia_hospital_carrasco.between(st.session_state.distancia_carrasco[0], st.session_state.distancia_carrasco[1]))
                        & (df.distancia_hospital_baigorria.between(st.session_state.distancia_baigorria[0], st.session_state.distancia_baigorria[1]))
                        & (df.area_util.between(st.session_state.area_util[0], st.session_state.area_util[1]))
                        & (df.banheiros.between(st.session_state.banheiros[0], st.session_state.banheiros[1]))
                        & (df.ambientes.between(st.session_state.ambientes[0], st.session_state.ambientes[1]))
                        & (df.dormitorios.between(st.session_state.dormitorios[0], st.session_state.dormitorios[1]))
                        & (df.aluguel_valor.between(st.session_state.aluguel_valor[0], st.session_state.aluguel_valor[1]))
                        & (df.expensas_valor.between(st.session_state.expensas_valor[0], st.session_state.expensas_valor[1]))
                        & (df.aluguel_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.aluguel_moeda) == 0 else st.session_state.aluguel_moeda
                            )
                        )
                        & (df.expensas_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.expensas_moeda) == 0 else st.session_state.expensas_moeda
                            )
                        )
                    ]
                )
                .reset_index(drop = True)
            )
        else:
            df_final = (
                df_zonaprop
                .pipe(
                    lambda df: df.loc[
                        (df.area_util.between(st.session_state.area_util[0], st.session_state.area_util[1]))
                        & (df.banheiros.between(st.session_state.banheiros[0], st.session_state.banheiros[1]))
                        & (df.ambientes.between(st.session_state.ambientes[0], st.session_state.ambientes[1]))
                        & (df.dormitorios.between(st.session_state.dormitorios[0], st.session_state.dormitorios[1]))
                        & (df.aluguel_valor.between(st.session_state.aluguel_valor[0], st.session_state.aluguel_valor[1]))
                        & (df.expensas_valor.between(st.session_state.expensas_valor[0], st.session_state.expensas_valor[1]))
                        & (df.aluguel_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.aluguel_moeda) == 0 else st.session_state.aluguel_moeda
                            )
                        )
                        & (df.expensas_moeda.isin(
                                ['$', 'USD', 'Sem info', 'Consultar precio'] if len(st.session_state.expensas_moeda) == 0 else st.session_state.expensas_moeda
                            )
                        )
                    ]
                )
                .reset_index(drop = True)
            )

    else:
        st.text('Selecione uma ou mais bases!')

    return df_final

def send_mail(df: pd.DataFrame, emails: str = None):
    '''
        Envia e-mail com os dados dos imóveis selecionados.

        Parâmetros:
        -----------
        df: pd.Dataframe
            Base de imóveis selecionados.
        email: str
            E-mail passado no sidebar.
    '''

    # Criando arquivo excel em memória
    excel_file = BytesIO()
    df.to_excel(excel_file, index=False)
    excel_file.seek(0)  # movendo cursor para o início do arquivo

    # Definindo o corpo do email
    corpo_email = textwrap.dedent(
        'Olá, confira abaixo a lista com os imóveis selecionados.'
    )

    # lista de emails
    lista_emails = [x for x in re.sub('\s+','', st.session_state.email_usuario).split(',')]

    # Loop para enviar um email por vez
    for i in range(0,len(lista_emails)):
        msg = MIMEMultipart()
        msg['Subject'] = f"Lista de imóveis selecionados"
        msg['From'] = os.getenv(key = "EMAIL")
        msg['To'] = lista_emails[i]
        senha = os.getenv(key = "EMAIL_PASSWORD")
        msg.add_header('Content-Type','text/html')
        # msg.set_payload(corpo_email)

        part = MIMEApplication(excel_file.getvalue(), Name = 'dataframe.xlsx')
        part['Content-Disposition'] = f'attachment; filename="dataframe.xlsx"'
        msg.attach(part)
        msg.attach(MIMEText(corpo_email, "plain"))

        # Definindo a conexão e enviando
        s = smtplib.SMTP('smtp.gmail.com: 587')
        s.starttls()
        s.login(msg['From'], senha)
        
        s.sendmail(
            msg['From'],
            [msg['To']],
            msg.as_string().encode('utf-8')
        )