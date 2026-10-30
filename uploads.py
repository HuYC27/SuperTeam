"""Room-scoped file admission and bounded document extraction."""
import base64
import io
import mimetypes
from pathlib import Path
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET

MAX_FILE=50*1024*1024
TEXT_LIMIT=40000

def extract_text(path):
    suffix=path.suffix.lower()
    if suffix=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(path)
        parts=[];count=0
        for i,page in enumerate(reader.pages):
            part=f'\n[第 {i+1} 页]\n'+(page.extract_text() or '')
            parts.append(part);count+=len(part)
            if count>TEXT_LIMIT:break
        text=''.join(parts)
        return text,('扫描 PDF 未提取出正文；可上传页面图片。' if not text.strip() or len(text.strip())<12 else '')
    if suffix=='.docx':
        with zipfile.ZipFile(path) as z:
            entry=z.getinfo('word/document.xml')
            if entry.file_size>20*1024*1024:raise ValueError('文档展开后过大')
            root=ET.fromstring(z.read(entry))
            ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            return '\n'.join(''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in root.findall('.//w:p',ns)),''
    if suffix=='.pptx':
        with zipfile.ZipFile(path) as z:
            names=sorted((n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)),key=lambda n:int(re.search(r'slide(\d+)',n).group(1)))
            if sum(z.getinfo(n).file_size for n in names)>50*1024*1024:raise ValueError('幻灯片文本展开后过大')
            parts=[]
            for i,name in enumerate(names):
                root=ET.fromstring(z.read(name));text='\n'.join(e.text or '' for e in root.iter() if e.tag.endswith('}t'))
                parts.append(f'[第 {i+1} 页]\n'+text)
                if sum(map(len,parts))>TEXT_LIMIT:break
            return '\n\n'.join(parts),'已提取逐页文字；图表和嵌入图片未自动识别，可另行上传图片。'
    if suffix=='.xls':
        import xlrd
        book=xlrd.open_workbook(path);parts=[];count=0
        for sheet in book.sheets():
            parts.append('工作表：'+sheet.name)
            for i in range(sheet.nrows):
                line='\t'.join(str(x) for x in sheet.row_values(i));parts.append(line);count+=len(line)
                if count>TEXT_LIMIT:break
            if count>TEXT_LIMIT:break
        return '\n'.join(parts),''
    if suffix=='.xlsx':
        from openpyxl import load_workbook
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('表格展开后过大')
        book=load_workbook(path,read_only=True,data_only=True);parts=[];count=0
        try:
            for sheet in book:
                parts.append('工作表：'+sheet.title)
                for row in sheet.iter_rows(values_only=True):
                    line='\t'.join('' if x is None else str(x) for x in row);parts.append(line);count+=len(line)
                    if count>TEXT_LIMIT:break
                if count>TEXT_LIMIT:break
        finally:book.close()
        return '\n'.join(parts),''
    allowed={'.txt','.md','.csv','.tsv','.json','.py','.r','.js','.ts','.html','.css','.yaml','.yml','.xml','.tex','.log','.ipynb','.sql','.c','.cpp','.h','.m','.toml','.ini','.sh','.ps1','.bib'}
    if suffix in allowed or not suffix:
        raw=path.read_bytes()
        if b'\x00' in raw:raise ValueError('该文件不是可读取的文本')
        for encoding in ['utf-8-sig','gb18030']:
            try:return raw.decode(encoding),''
            except UnicodeDecodeError:continue
        raise ValueError('无法识别文本编码，请转换为 UTF-8')
    return '', '此格式暂不自动提取正文；AI 可在权限允许时使用本地工具读取。'

def save_upload(store,root,rid,name,mime,data):
    store.room(rid)
    if not isinstance(name,str) or not name or len(name)>200:raise ValueError('文件名无效')
    if not isinstance(data,str) or len(data)>MAX_FILE*4//3+8:raise ValueError('每个文件最多 50 MB')
    try:raw=base64.b64decode(data,validate=True)
    except Exception as exc:raise ValueError('文件编码无效') from exc
    if len(raw)>MAX_FILE:raise ValueError('每个文件最多 50 MB')
    safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',name).strip('. ') or 'file'
    aid=uuid.uuid4().hex;kind='file';actual=mimetypes.guess_type(safe)[0] or 'application/octet-stream'
    is_image=Path(safe).suffix.lower() in {'.png','.jpg','.jpeg','.webp','.gif','.bmp','.tif','.tiff','.ico','.avif','.heic','.heif'} or str(mime).startswith('image/')
    model_raw=None;image_note=''
    if is_image:
        from PIL import Image,ImageOps
        try:
            try:
                import pillow_heif
                pillow_heif.register_heif_opener()
            except ImportError:pass
            try:import pillow_avif
            except ImportError:pass
            with Image.open(io.BytesIO(raw)) as image:
                if image.width*image.height>100000000:raise ValueError('图片最多支持 1 亿像素，请缩小后重试')
                image.load();actual=Image.MIME.get(image.format,'application/octet-stream')
                animated=getattr(image,'n_frames',1)>1
                image=ImageOps.exif_transpose(image).convert('RGBA');before=image.size;image.thumbnail((4096,4096))
                out=io.BytesIO();image.save(out,format='PNG');model_raw=out.getvalue()
                image_note='已创建 PNG 兼容预览；上传的原件仍保留。'
                if before!=image.size:image_note+=' 模型预览已缩放至最长边 4096 像素。'
                if animated:image_note+=' 动态图片仅分析首帧。'
        except ValueError:raise
        except Exception as exc:raise ValueError('这张图片暂时无法解码，请尝试导出为 PNG 或 JPEG 再上传。原因为 '+type(exc).__name__) from exc
        kind='image'
    folder=Path(root)/'work'/'rooms'/rid/'inputs';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(aid+'-'+safe);path.write_bytes(raw)
    try:
        text,note=('', image_note) if kind=='image' else extract_text(path)
        model_path=None
        if model_raw is not None:
            model_path=folder/(aid+'-preview.png');model_path.write_bytes(model_raw)
        if len(text)>TEXT_LIMIT:text=text[:TEXT_LIMIT];note=(note+' 正文超过上限，已截取前 40000 字符。').strip()
        return store.add_attachment(rid,aid,safe,actual,kind,str(path),len(raw),text,note,str(model_path) if model_path else '')
    except ValueError:
        path.unlink(missing_ok=True);raise
    except Exception as exc:
        path.unlink(missing_ok=True);raise ValueError('无法提取文件正文，请检查文件是否损坏、加密或格式不符。') from exc
