#!/usr/bin/env python3
"""
临时诊断脚本：测试 maps.co API
"""
import os
import requests
from urllib.parse import quote
from dotenv import load_dotenv

# 加载 .env
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
API_KEY = os.getenv("MAPS_CO_API_KEY", "").strip()

print("=" * 60)
print("Maps.co API 诊断工具")
print("=" * 60)

# 1. 检查 API key
print(f"\n1. API Key 检查:")
if API_KEY:
    print(f"   ✅ API Key 已加载: {API_KEY[:10]}...{API_KEY[-5:]}")
else:
    print(f"   ❌ API Key 未设置")
    exit(1)

# 2. 测试简单查询
print(f"\n2. 测试查询: 'Beijing'")
test_query = "Beijing"
url = f"https://geocode.maps.co/search?q={quote(test_query)}&api_key={API_KEY}"
print(f"   URL: {url[:80]}...")

try:
    res = requests.get(url, timeout=10)
    print(f"   状态码: {res.status_code}")
    print(f"   响应头: {dict(res.headers)}")
    
    if res.status_code == 200:
        data = res.json()
        print(f"   响应数据类型: {type(data)}")
        print(f"   结果数量: {len(data) if isinstance(data, list) else 'N/A'}")
        
        if data:
            print(f"   ✅ 查询成功！")
            print(f"   第一个结果: {data[0]}")
        else:
            print(f"   ⚠️ 查询成功但返回空数组")
    else:
        print(f"   ❌ API 返回错误码: {res.status_code}")
        print(f"   响应内容: {res.text[:500]}")
        
except Exception as e:
    print(f"   ❌ 请求失败: {e}")

# 3. 测试真实机构名
print(f"\n3. 测试真实机构: 'Roseman University of Health Sciences'")
test_query2 = "Roseman University of Health Sciences"
url2 = f"https://geocode.maps.co/search?q={quote(test_query2)}&api_key={API_KEY}"

try:
    res2 = requests.get(url2, timeout=10)
    print(f"   状态码: {res2.status_code}")
    
    if res2.status_code == 200:
        data2 = res2.json()
        print(f"   结果数量: {len(data2) if isinstance(data2, list) else 'N/A'}")
        
        if data2:
            print(f"   ✅ 找到结果")
            first = data2[0]
            print(f"   坐标: ({first.get('lat')}, {first.get('lon')})")
            print(f"   地址: {first.get('display_name', 'N/A')}")
        else:
            print(f"   ⚠️ 无结果（机构名可能不在数据库）")
    else:
        print(f"   ❌ API 错误: {res2.status_code}")
        print(f"   响应: {res2.text[:500]}")
        
except Exception as e:
    print(f"   ❌ 请求失败: {e}")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
