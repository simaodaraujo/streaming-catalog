import os
import io
from PIL import Image, ImageDraw, ImageFont

def get_badge_font(size, bold=True):
    candidates = ['arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSans.ttf', 'FreeSansBold.ttf'] if bold else ['arial.ttf', 'DejaVuSans.ttf', 'FreeSans.ttf']
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()

def draw_rank_badge(poster_bytes, rank, variation):
    """
    Desenha um badge pílula moderno compacto estilo FlixPatrol no canto superior esquerdo do poster.
    Sem exibição do número de ranking #rank.
    Margem de segurança anti-corte ampliada para evitar cortes nos cantos do Stremio.
    """
    if not Image or not ImageDraw or not ImageFont:
        return poster_bytes

    try:
        img = Image.open(io.BytesIO(poster_bytes)).convert("RGBA")
        w, h = img.size

        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        scale = w / 500.0
        margin_x = int(26 * scale)
        margin_y = int(24 * scale)
        badge_h = max(24, int(29 * scale))
        radius = badge_h // 2

        font_size = max(11, int(13.5 * scale))
        font_badge = get_badge_font(font_size, bold=True)

        if variation.startswith('+'):
            var_text = f"▲ {variation}"
            var_color = (74, 222, 128, 255)       # Verde esmeralda (#4ADE80)
            outline_color = (74, 222, 128, 110)   # Borda sutil esmeralda
            fill_color = (12, 24, 16, 235)         # Fundo escuro esverdeado translúcido
        elif variation.startswith('-'):
            var_text = f"▼ {variation}"
            var_color = (248, 113, 113, 255)      # Vermelho coral (#F87171)
            outline_color = (248, 113, 113, 110)  # Borda sutil vermelha
            fill_color = (26, 12, 14, 235)        # Fundo escuro avermelhado translúcido
        elif variation == 'NOVO':
            var_text = "★ NOVO"
            var_color = (250, 204, 21, 255)       # Dourado (#FACC15)
            outline_color = (250, 204, 21, 110)   # Borda sutil dourada
            fill_color = (26, 22, 10, 235)        # Fundo escuro dourado translúcido
        else:
            var_text = "="
            var_color = (203, 213, 225, 255)      # Cinzento neutro (#CBD5E1)
            outline_color = (203, 213, 225, 65)   # Borda sutil neutra
            fill_color = (15, 17, 23, 235)        # Fundo escuro neutro translúcido

        # Medição precisa do texto
        t_bbox = draw.textbbox((0, 0), var_text, font=font_badge)
        text_w = t_bbox[2] - t_bbox[0]
        
        # Padding horizontal simétrico
        pad_x = int(10 * scale) if var_text != "=" else int(13 * scale)
        badge_w = max(badge_h, text_w + 2 * pad_x)

        box = [margin_x, margin_y, margin_x + badge_w, margin_y + badge_h]
        border_w = max(1, int(1.2 * scale))

        # Desenho da pílula
        draw.rounded_rectangle(box, radius=radius, fill=fill_color, outline=outline_color, width=border_w)

        # Centralização exata do texto
        center_x = margin_x + badge_w / 2.0
        center_y = margin_y + badge_h / 2.0
        try:
            draw.text((center_x, center_y), var_text, font=font_badge, fill=var_color, anchor="mm")
        except TypeError:
            # Fallback caso a versão do Pillow não suporte anchor="mm"
            text_h = t_bbox[3] - t_bbox[1]
            tx = margin_x + (badge_w - text_w) / 2.0
            ty = margin_y + (badge_h - text_h) / 2.0
            draw.text((tx, ty), var_text, font=font_badge, fill=var_color)

        final_img = Image.alpha_composite(img, overlay).convert("RGB")
        output = io.BytesIO()
        final_img.save(output, format="JPEG", quality=90)
        return output.getvalue()
    except Exception as e:
        print(f"  [!] Erro ao desenhar badge: {e}", flush=True)
        return poster_bytes

def main():
    os.makedirs("test_badges", exist_ok=True)
    # Usa um poster existente como base
    base_poster_path = "dist/posters/netflix_pt_movies_1.jpg"
    if not os.path.exists(base_poster_path):
        # Cria uma imagem de teste 500x750 se não existir
        img = Image.new("RGB", (500, 750), (35, 38, 48))
        d = ImageDraw.Draw(img)
        d.text((100, 350), "TEST POSTER", fill=(200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        poster_bytes = buf.getvalue()
    else:
        with open(base_poster_path, "rb") as f:
            poster_bytes = f.read()

    test_cases = [
        ("pill_up.jpg", 2, "+2"),
        ("pill_down.jpg", 5, "-3"),
        ("pill_same.jpg", 3, "="),
        ("pill_novo.jpg", 1, "NOVO"),
    ]

    for filename, rank, var in test_cases:
        out_bytes = draw_rank_badge(poster_bytes, rank, var)
        out_path = os.path.join("test_badges", filename)
        with open(out_path, "wb") as f:
            f.write(out_bytes)
        print(f"Gerado: {out_path} ({var})")

if __name__ == "__main__":
    main()
