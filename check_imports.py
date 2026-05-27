import importlib 
mods = ['file_parser','normality','capability','control_charts','gauge_rr','capa_rules_engine','pdf_report'] 
[print('OK:', m) if not hasattr(__import__('importlib').import_module(m), '__') else None for m in mods] 
