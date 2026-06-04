from scripts.generate_image     import gerar_imagem
from scripts.generate_script    import gerar_roteiro
from scripts.generate_voice     import gerar_narracao
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
import os

# V1: Geração de vídeo único quando executado

tema = "O celular não é o culpado da sua procrastinação"
base_out_path = os.path.join(os.getcwd(), 'video_gerado')

if not os.path.exists(base_out_path):
    os.makedirs(base_out_path)

roteiro = gerar_roteiro("Gere um roteiro sobre" + tema)
print("Roteiro gerado! Salvando...")
frases_roteiro = roteiro[0]
prompts_imagens = roteiro[1]
arquivo_roteiro = "roteiro.txt"
arquivo_prompts = "prompts.txt"

with open(os.path.join(base_out_path, arquivo_roteiro), "a", encoding="utf-8") as arquivo:
    for frase in frases_roteiro:
        arquivo.write(f"\n{frase[1]}")
        
print("Roteiro salvo em: ", os.path.join(base_out_path, arquivo_roteiro))
        
with open(os.path.join(base_out_path, arquivo_prompts), "a", encoding="utf-8") as arquivo:
    for prompt in prompts_imagens:
        arquivo.write(f"\n{prompt[1]}")
        
print("Prompts salvos em: ", os.path.join(base_out_path, arquivo_prompts))

caminho_narracao = os.path.join(base_out_path, "audio")
if not os.path.exists(caminho_narracao):
    os.makedirs(caminho_narracao)

for i, frase in enumerate(frases_roteiro):
    gerar_narracao(frase[1], os.path.join(caminho_narracao, ("frase_" + str(i+1) + ".mp3")))
    print(f"Narração {i+1} gerada com sucesso!")


caminho_imagens = os.path.join(base_out_path, "images")
if not os.path.exists(caminho_imagens):
    os.makedirs(caminho_imagens)
    
for i, prompt in enumerate(prompts_imagens):
    imagem = gerar_imagem(prompt[1], "16:9", os.path.join("assets", "imagem_referencia.png"))
    caminho_arquivo = os.path.join(caminho_imagens, f"imagem_{i+1}.png")
    with open(caminho_arquivo, 'wb') as arquivo:
        arquivo.write(imagem)
    print(f"Imagem {i+1} gerada com sucesso!")


print("Montando o vídeo final...")
clipes = []

for i, frase in enumerate(frases_roteiro):
    caminho_audio = os.path.join(caminho_narracao, f"frase_{i+1}.mp3")
    caminho_imagem = os.path.join(caminho_imagens, f"imagem_{i+1}.png")
    
    audio = AudioFileClip(caminho_audio)
    clipe = ImageClip(caminho_imagem).with_duration(audio.duration).with_audio(audio)
    clipes.append(clipe)
    print(f"Cena {i+1} montada ({audio.duration:.2f}s)")

video_final = concatenate_videoclips(clipes, method="compose")
caminho_video = os.path.join(base_out_path, "video_final.mp4")
video_final.write_videofile(caminho_video, fps=24, codec="libx264", audio_codec="aac")

print("Vídeo gerado com sucesso em:", caminho_video)