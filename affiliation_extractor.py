"""
DOI页面爬虫：从论文网页中提取机构信息
支持主流出版商：IEEE, Springer, Elsevier, Nature, ACM, Wiley等
"""
import requests
from bs4 import BeautifulSoup
import re
import time

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

class AffiliationExtractor:
    def __init__(self):
        self.cache = {}  # 简单内存缓存
        self.failed_urls = set()  # 记录失败的URL，避免重复尝试
    
    def extract_from_doi(self, doi_url, timeout=8):
        """
        从DOI链接提取机构信息
        返回: list of affiliation strings
        """
        if not doi_url or not doi_url.startswith('http'):
            return []
        
        # 检查缓存
        if doi_url in self.cache:
            return self.cache[doi_url]
        
        # 检查是否已知失败
        if doi_url in self.failed_urls:
            return []
        
        try:
            headers = {
                'User-Agent': USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            res = requests.get(doi_url, headers=headers, timeout=timeout, allow_redirects=True)
            
            if res.status_code != 200:
                print(f"[AffExtractor] HTTP {res.status_code} for {doi_url}")
                self.failed_urls.add(doi_url)
                return []
            
            # 检测是否被反爬拦截
            if 'captcha' in res.text.lower() or 'bot' in res.text.lower() or len(res.text) < 1000:
                print(f"[AffExtractor] 可能被反爬拦截: {doi_url[:50]}")
                self.failed_urls.add(doi_url)
                self.cache[doi_url] = []
                return []
            
            # 判断出版商
            final_url = res.url.lower()
            html = res.text
            
            affiliations = []
            
            if 'ieeexplore.ieee.org' in final_url:
                affiliations = self._extract_ieee(html)
            elif 'springer.com' in final_url or 'link.springer.com' in final_url:
                affiliations = self._extract_springer(html)
            elif 'sciencedirect.com' in final_url:
                affiliations = self._extract_elsevier(html)
            elif 'nature.com' in final_url:
                affiliations = self._extract_nature(html)
            elif 'acm.org' in final_url:
                affiliations = self._extract_acm(html)
            elif 'wiley.com' in final_url:
                affiliations = self._extract_wiley(html)
            elif 'iopscience.iop.org' in final_url:
                affiliations = self._extract_iop(html)
            else:
                # 通用方法
                affiliations = self._extract_generic(html)
            
            # 清洗数据
            affiliations = self._clean_affiliations(affiliations)
            
            # 缓存结果
            self.cache[doi_url] = affiliations
            
            if affiliations:
                print(f"[AffExtractor] ✓ 提取到 {len(affiliations)} 个机构: {affiliations[0][:50]}")
            
            return affiliations
            
        except requests.Timeout:
            print(f"[AffExtractor] ⏱️ 超时: {doi_url}")
            return []
        except Exception as e:
            print(f"[AffExtractor] ⚠️ 错误: {e}")
            return []
    
    def _extract_ieee(self, html):
        """提取IEEE论文的机构信息"""
        soup = BeautifulSoup(html, 'html.parser')
        affiliations = []
        
        # IEEE格式1: author-card中的affiliation
        cards = soup.find_all('div', class_='author-card')
        for card in cards:
            aff_div = card.find('div', class_='affiliation')
            if aff_div:
                affiliations.append(aff_div.get_text(strip=True))
        
        # IEEE格式2: 作者信息中的sup标记
        if not affiliations:
            author_info = soup.find('div', class_='authors-info')
            if author_info:
                for aff in author_info.find_all(['div', 'span'], class_=re.compile('affiliation')):
                    affiliations.append(aff.get_text(strip=True))
        
        return affiliations
    
    def _extract_springer(self, html):
        """提取Springer论文的机构信息"""
        soup = BeautifulSoup(html, 'html.parser')
        affiliations = []
        
        # Springer格式: c-article-author-affiliation__address
        for aff in soup.find_all('div', class_=re.compile('author-affiliation|affiliation__address')):
            text = aff.get_text(strip=True)
            if text and len(text) > 10:
                affiliations.append(text)
        
        return affiliations
    
    def _extract_elsevier(self, html):
        """提取Elsevier/ScienceDirect论文的机构信息"""
        soup = BeautifulSoup(html, 'html.parser')
        affiliations = []
        
        # Elsevier格式: author-group中的affiliation
        for group in soup.find_all('dl', class_='author-group'):
            for aff in group.find_all('dd', id=re.compile('aff')):
                affiliations.append(aff.get_text(strip=True))
        
        return affiliations
    
    def _extract_nature(self, html):
        """提取Nature系列论文的机构信息"""
        soup = BeautifulSoup(html, 'html.parser')
        affiliations = []
        
        # Nature格式: c-article-author-affiliation
        for aff in soup.find_all(['p', 'div'], class_=re.compile('affiliation')):
            text = aff.get_text(strip=True)
            if text and len(text) > 10:
                affiliations.append(text)
        
        return affiliations
    
    def _extract_acm(self, html):
        """提取ACM论文的机构信息"""
        soup = BeautifulSoup(html, 'html.parser')
        affiliations = []
        
        # ACM格式: author-institution
        for inst in soup.find_all(['div', 'span'], class_=re.compile('institution|affiliation')):
            text = inst.get_text(strip=True)
            if text and len(text) > 10:
                affiliations.append(text)
        
        return affiliations
    
    def _extract_wiley(self, html):
        """提取Wiley论文的机构信息"""
        soup = BeautifulSoup(html, 'html.parser')
        affiliations = []
        
        for aff in soup.find_all(['div', 'p'], class_=re.compile('affiliation')):
            text = aff.get_text(strip=True)
            if text and len(text) > 10:
                affiliations.append(text)
        
        return affiliations
    
    def _extract_iop(self, html):
        """提取IOP (Institute of Physics)论文的机构信息"""
        soup = BeautifulSoup(html, 'html.parser')
        affiliations = []
        
        # IOP格式: 作者信息中的affiliation
        for aff in soup.find_all(['p', 'div'], class_=re.compile('affiliation|institution')):
            text = aff.get_text(strip=True)
            if text and len(text) > 10:
                affiliations.append(text)
        
        return affiliations
    
    def _extract_generic(self, html):
        """通用提取方法：适用于未知出版商"""
        soup = BeautifulSoup(html, 'html.parser')
        affiliations = []
        
        # 方法1: 查找包含"affiliation"关键词的标签
        for tag in soup.find_all(['div', 'p', 'span'], class_=re.compile('affiliation|institution', re.I)):
            text = tag.get_text(strip=True)
            if text and 10 < len(text) < 200:
                affiliations.append(text)
        
        # 方法2: 查找包含"University"或"Institute"的段落
        if not affiliations:
            for p in soup.find_all('p'):
                text = p.get_text(strip=True)
                if ('University' in text or 'Institute' in text or 'College' in text) and 10 < len(text) < 200:
                    affiliations.append(text)
        
        return affiliations[:5]  # 最多返回5个
    
    def _clean_affiliations(self, affiliations):
        """清洗机构名称"""
        cleaned = []
        
        for aff in affiliations:
            # 去除多余空白
            aff = ' '.join(aff.split())
            
            # 去除常见的无用前缀
            aff = re.sub(r'^[\d\*\†\‡]+\s*', '', aff)
            
            # 去除邮箱地址
            aff = re.sub(r'\S+@\S+', '', aff)
            
            # 去除多余的标点
            aff = aff.strip(',;. ')
            
            # 长度过滤
            if 10 < len(aff) < 300:
                cleaned.append(aff)
        
        # 去重
        return list(dict.fromkeys(cleaned))

# 全局单例
extractor = AffiliationExtractor()
