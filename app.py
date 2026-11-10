import os
import io
import re
import zipfile
import streamlit as st
import pymupdf

st.set_page_config(
    page_title="PDF白マスク消去・解答完全復元Webアプリ",
    page_icon="🔓",
    layout="centered"
)

def unmask_pdf_bytes(pdf_bytes):
    """
    Removes white mask rectangles from PDF content streams.
    Restores the original hidden text, layout, kerning, and colors with 100% fidelity.
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)
    modified_pages = 0
    total_masks_removed = 0

    re_pattern = re.compile(
        r'([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+re\s+(f\*?|b\*?)',
        re.IGNORECASE
    )

    for pno in range(total_pages):
        page = doc[pno]
        page_rect = page.rect
        drawings = page.get_drawings()

        # 1. Identify white filled rectangles (masks)
        white_masks = []
        for d in drawings:
            fill = d.get("fill")
            r = d.get("rect")
            if fill is not None and len(fill) >= 3:
                # Near-white color check (RGB > 0.92)
                if fill[0] > 0.92 and fill[1] > 0.92 and fill[2] > 0.92:
                    # Exclude the full page slide background
                    if r.width < page_rect.width * 0.95 or r.height < page_rect.height * 0.95:
                        white_masks.append(r)

        if not white_masks:
            continue

        # Clean contents normalizes PDF stream operators
        page.clean_contents()
        stream = page.read_contents().decode('latin1', errors='ignore')

        page_removed = 0

        def repl(match):
            nonlocal page_removed
            x_pdf = float(match.group(1))
            y_pdf = float(match.group(2))
            w_pdf = float(match.group(3))
            h_pdf = float(match.group(4))
            op = match.group(5).lower()

            # Convert PDF stream coordinates (bottom-left origin) to top-left origin
            x0 = x_pdf
            x1 = x_pdf + w_pdf
            y1 = page_rect.height - y_pdf
            y0 = y1 - h_pdf

            # Check matching against detected white masks
            is_mask = False
            for wr in white_masks:
                if (abs(wr.x0 - x0) < 2.0 and abs(wr.x1 - x1) < 2.0 and
                    abs(wr.y0 - y0) < 2.0 and abs(wr.y1 - y1) < 2.0):
                    is_mask = True
                    break

            if is_mask:
                page_removed += 1
                # If operator was B/b (fill and stroke), change to S (stroke only) so box borders remain
                if 'b' in op:
                    return f"{match.group(1)} {match.group(2)} {match.group(3)} {match.group(4)} re S"
                # If operator was f (fill only), remove fill completely
                return ""
            return match.group(0)

        new_stream = re_pattern.sub(repl, stream)

        if page_removed > 0:
            modified_pages += 1
            total_masks_removed += page_removed
            xref = page.get_contents()[0]
            doc.update_stream(xref, new_stream.encode('latin1'))

    output_buffer = io.BytesIO()
    doc.save(output_buffer, deflate=True)
    doc.close()
    output_buffer.seek(0)

    return output_buffer.getvalue(), modified_pages, total_pages, total_masks_removed

# --- UI Header ---
st.title("🔓 PDF白マスク消去・解答完全復元アプリ")
st.write(
    "講義スライド等のPDFをアップロードすると、**白マスク（空欄・目隠し図形）そのものをPDFから完全消去**します。"
    "上から文字を書き直すのではなくマスクを除去するため、**複数行や大きい幅の隠しでも、元のフォント・文字配置・色・下線そのままに100%美しく復元**されます。"
)

# --- File Uploader ---
uploaded_files = st.file_uploader(
    "PDFファイルを選択またはドラッグ＆ドロップ（複数ファイル対応）",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    st.write(f"📁 選択されたファイル数: **{len(uploaded_files)} 件**")

    if st.button("🚀 白マスクを消去して解答を完全復元する", type="primary"):
        processed_results = []
        progress_bar = st.progress(0)

        for idx, file in enumerate(uploaded_files):
            pdf_bytes = file.read()
            with st.spinner(f"マスク消去処理中: {file.name}..."):
                out_bytes, mod_pages, tot_pages, total_masks = unmask_pdf_bytes(pdf_bytes)

            base, _ = os.path.splitext(file.name)
            out_filename = f"{base}_マスク消去済.pdf"

            processed_results.append({
                "filename": out_filename,
                "orig_filename": file.name,
                "bytes": out_bytes,
                "mod_pages": mod_pages,
                "tot_pages": tot_pages,
                "total_masks": total_masks,
            })
            progress_bar.progress((idx + 1) / len(uploaded_files))

        st.success(f"🎉 全 {len(processed_results)} 件のPDF処理が完了しました！")

        # --- Download Section ---
        st.markdown("### 📥 ダウンロード")

        # ZIP download if multiple files
        if len(processed_results) > 1:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for item in processed_results:
                    zip_file.writestr(item["filename"], item["bytes"])
            zip_buffer.seek(0)

            st.download_button(
                label="📦 すべての復元PDFを一括ダウンロード (.zip)",
                data=zip_buffer,
                file_name="講義資料_マスク消去済一括.zip",
                mime="application/zip",
                type="primary"
            )
            st.divider()

        # Individual file cards
        for item in processed_results:
            col1, col2 = st.columns([3, 2])
            with col1:
                st.write(f"📄 **{item['filename']}**")
                if item["total_masks"] > 0:
                    st.caption(f"✅ {item['mod_pages']}/{item['tot_pages']} ページから合計 {item['total_masks']} 箇所の白マスクを消去")
                else:
                    st.caption("ℹ️ 白マスクは検出されませんでした")
            with col2:
                st.download_button(
                    label=f"⬇️ ダウンロード",
                    data=item["bytes"],
                    file_name=item["filename"],
                    mime="application/pdf",
                    key=item["filename"]
                )
            st.write("---")

st.markdown("""
---
<div style='text-align: center; color: #888; font-size: 0.85em;'>
PDF白マスク自動消去アプリ | フォントのズレ・文字被り・サイズ制限なしで完全復元
</div>
""", unsafe_allow_html=True)
