import json
import os
import pandas as pd

def generate_master():
    print("🚀 JPX銘柄データ (data_j.xlsx) から詳細マスターの生成を開始します...")
    
    excel_path = None
    for filename in ["data_j.xlsx", "data_j.xls"]:
        if os.path.exists(filename):
            excel_path = filename
            break
    
    if not excel_path:
        print("❌ エラー: フォルダ内に 『data_j.xlsx』 または 『data_j.xls』 が見つかりません。")
        return

    print(f"📖 『{excel_path}』 を解析中...")
    df = pd.read_excel(excel_path)

    master_dict = {}
    for _, row in df.iterrows():
        code = str(row['コード']).strip().zfill(4)
        name = str(row['銘柄名']).strip()
        market = str(row.get('市場・商品区分', '不明')).strip()
        sector = str(row.get('33業種区分', '不明')).strip()

        if len(code) == 4 and code.isdigit() and name:
            master_dict[code] = {
                "name": name,
                "market": market,
                "sector": sector
            }

    if not master_dict:
        raise ValueError("取得したデータが空です。")

    with open("jpx_master.json", "w", encoding="utf-8") as f:
        json.dump(master_dict, f, ensure_ascii=False, indent=2)

    print(f"✅ 成功！ 全 {len(master_dict)} 銘柄の詳細マスター 『jpx_master.json』 を生成しました！")

if __name__ == "__main__":
    generate_master()