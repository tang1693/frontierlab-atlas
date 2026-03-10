"""
PDF Affiliation Extractor
从论文PDF中提取机构信息（内存处理，不保存文件）
"""
import requests
import re
import io
from typing import List, Tuple

try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("[PDFExtractor] ⚠️ PyPDF2 not installed. PDF extraction disabled.")

class PDFAffiliationExtractor:
    def __init__(self):
        self.cache = {}  # DOI -> affiliations
        
        # 机构关键词模式
        self.institution_patterns = [
            r'University\s+of\s+[\w\s]+',
            r'[\w\s]+\s+University',
            r'[\w\s]+\s+Institute(?:\s+of[\w\s]+)?',
            r'[\w\s]+\s+College',
            r'[\w\s]+\s+Laboratory',
            r'School\s+of\s+[\w\s]+',
            r'Department\s+of\s+[\w\s]+',
            r'Faculty\s+of\s+[\w\s]+',
            r'Center\s+for\s+[\w\s]+',
            r'Academy\s+of\s+[\w\s]+',
        ]
        
    def extract_from_pdf_url(self, pdf_url: str, timeout: int = 15) -> List[str]:
        """
        从PDF URL提取机构信息
        返回: list of affiliation strings
        """
        if not PDF_AVAILABLE:
            return []
        
        if not pdf_url or not pdf_url.startswith('http'):
            return []
        
        # 检查缓存
        if pdf_url in self.cache:
            return self.cache[pdf_url]
        
        try:
            print(f"[PDFExtractor] 下载PDF: {pdf_url[:60]}...")
            
            # 下载PDF到内存
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
            
            if response.status_code != 200:
                print(f"[PDFExtractor] HTTP {response.status_code}")
                return []
            
            # 检查是否真的是PDF
            content_type = response.headers.get('Content-Type', '')
            if 'pdf' not in content_type.lower():
                print(f"[PDFExtractor] Not a PDF: {content_type}")
                return []
            
            # 在内存中处理PDF
            pdf_bytes = io.BytesIO(response.content)
            
            # 提取文本
            text = self._extract_text_from_pdf(pdf_bytes)
            
            if not text:
                print(f"[PDFExtractor] 无法提取文本")
                return []
            
            # 从文本中提取机构
            affiliations = self._extract_affiliations_from_text(text)
            
            # 缓存结果
            self.cache[pdf_url] = affiliations
            
            if affiliations:
                print(f"[PDFExtractor] ✓ 提取到 {len(affiliations)} 个机构")
            
            return affiliations
            
        except requests.Timeout:
            print(f"[PDFExtractor] ⏱️ 超时")
            return []
        except Exception as e:
            print(f"[PDFExtractor] ⚠️ 错误: {type(e).__name__}: {str(e)[:50]}")
            return []
    
    def _extract_text_from_pdf(self, pdf_file: io.BytesIO, max_pages: int = 2) -> str:
        """从PDF提取前N页的文本"""
        try:
            reader = PyPDF2.PdfReader(pdf_file)
            
            # 只读取前2页（作者信息通常在第一页）
            pages_to_read = min(len(reader.pages), max_pages)
            
            text = ""
            for i in range(pages_to_read):
                page = reader.pages[i]
                text += page.extract_text() + "\n"
            
            return text
            
        except Exception as e:
            print(f"[PDFExtractor] PDF解析错误: {e}")
            return ""
    
    def _extract_affiliations_from_text(self, text: str) -> List[str]:
        """
        从PDF文本中提取机构信息
        使用多种模式匹配
        """
        affiliations = []
        
        # 清理文本
        text = ' '.join(text.split())  # 合并多余空白
        
        # 方法1: 使用正则模式匹配
        for pattern in self.institution_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                aff = match.group(0).strip()
                
                # 基本清洗
                aff = self._clean_affiliation(aff)
                
                # 长度过滤
                if 10 < len(aff) < 150:
                    affiliations.append(aff)
        
        # 方法2: 查找常见的机构名称格式
        # 格式：^1Department of XXX, University of YYY
        superscript_pattern = r'[\d\*†‡]+\s*([\w\s,]+(?:University|Institute|College)[^\n]{0,100})'
        for match in re.finditer(superscript_pattern, text, re.IGNORECASE):
            aff = match.group(1).strip()
            aff = self._clean_affiliation(aff)
            if 10 < len(aff) < 150:
                affiliations.append(aff)
        
        # 去重
        affiliations = list(dict.fromkeys(affiliations))
        
        return affiliations[:5]  # 最多返回5个
    
    def _clean_affiliation(self, aff: str) -> str:
        """清洗机构名称"""
        # 去除邮箱
        aff = re.sub(r'\S+@\S+', '', aff)
        
        # 去除多余的标点
        aff = aff.strip(',;. ')
        
        # 去除换行符
        aff = ' '.join(aff.split())
        
        return aff

# 全局单例
pdf_extractor = PDFAffiliationExtractor()
