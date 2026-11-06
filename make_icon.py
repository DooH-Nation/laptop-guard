from PIL import Image, ImageDraw
from pathlib import Path
out=Path(__file__).parent

def icon(color):
    s=256
    im=Image.new('RGBA',(s,s),(0,0,0,0))
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((8,8,248,248),radius=58,fill='#101c36')
    d.polygon([(128,32),(207,61),(201,143),(177,187),(128,223),(79,187),(55,143),(49,61)],fill=color)
    d.polygon([(128,48),(191,71),(186,139),(165,176),(128,204),(91,176),(70,139),(65,71)],fill='#172844')
    d.rounded_rectangle((87,96,169,153),radius=9,fill='#f2f8ff')
    d.rectangle((95,103,161,144),fill='#172844')
    d.rounded_rectangle((76,158,180,168),radius=5,fill='#f2f8ff')
    d.line([(111,124),(124,137),(150,110)],fill=color,width=10)
    return im

if __name__=='__main__':
    icon('#51dbc0').save(out/'LaptopGuard.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    icon('#51dbc0').save(out/'LaptopGuard-icon.png')
