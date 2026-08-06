import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
# ... 나머지 그대로


st.title("hello")

st.write("1. Tracker 로드 시도...")
from services.cv.track import Tracker
tracker = Tracker()
st.write("2. Tracker 성공")

st.write("3. Searcher 로드 시도...")
from taek.search import Searcher
searcher = Searcher()
st.write("4. Searcher 성공")