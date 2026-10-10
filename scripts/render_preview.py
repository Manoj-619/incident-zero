"""Generate the README's animated mission projection from the actual recorded tool output.

Requires Pillow (optional presentation dependency); this is not a screenshot of the dashboard.
"""
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
result = json.loads((ROOT/'frontend/public/demo/crossing.json').read_text())['result']
WIDTH, HEIGHT = 960, 540
font_path = '/usr/share/fonts/truetype/dejavu/'

def font(size, bold=False):
    return ImageFont.truetype(font_path+('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'),size)


def project(position):
    x,y,z = [value/6378.137 for value in position]
    # Fixed orthographic ECI projection, same transform for every object.
    angle=.65
    u=x*math.cos(angle)-y*math.sin(angle)
    v=(x*math.sin(angle)+y*math.cos(angle))*.52-z*.85
    return (int(650+u*170),int(278+v*170))


frames=[]
for frame in range(72):
    image=Image.new('RGB',(WIDTH,HEIGHT),'#060b13');draw=ImageDraw.Draw(image)
    for x in range(0,WIDTH,40):draw.line((x,0,x,HEIGHT),fill='#0c1723')
    for y in range(0,HEIGHT,40):draw.line((0,y,WIDTH,y),fill='#0c1723')
    draw.text((34,27),'ORBIT SENTINEL',font=font(27,True),fill='#dce8f0')
    draw.text((35,66),'RECORDED SYNTHETIC MISSION / ORTHOGRAPHIC PROJECTION',font=font(9),fill='#7894a8')
    draw.line((35,91,925,91),fill='#233746')
    draw.ellipse((480,108,820,448),fill='#0d2939',outline='#2d6474',width=2)
    for width in (70,140,240):draw.ellipse((650-width/2,108,650+width/2,448),outline='#1d4659')
    for height in (60,140,250):draw.ellipse((480,278-height/2,820,278+height/2),outline='#1d4659')
    after=frame>=36
    paths=[result['after_trajectory'] if after else result['objects'][0],*result['objects'][1:]]
    index=int((frame%36)/35*(len(paths[0]['positions_km'])-1))
    colors=['#58e5cb','#ff826e','#6e8bfd']
    for path,color in zip(paths,colors,strict=True):
        points=[project(position) for position in path['positions_km']]
        draw.line(points,fill=color,width=2)
        px,py=points[index];draw.ellipse((px-4,py-4,px+4,py+4),fill=color)
    draw.text((35,125),'MANEUVER PREVIEW' if after else 'BASELINE / CONJUNCTION',font=font(14,True),fill='#58e5cb' if after else '#ff826e')
    event=result['after'][0] if after else result['baseline'][0]
    draw.text((35,175),'NOMINAL MISS DISTANCE',font=font(10),fill='#7894a8')
    draw.text((35,195),f"{event['miss_distance_m']:.1f} m",font=font(36,True),fill='#dce8f0')
    draw.text((35,255),'WORST STRESSED COLLISION RISK',font=font(10),fill='#7894a8')
    draw.text((35,277),f"{event['worst_stress_probability']:.2e}",font=font(30),fill='#58e5cb' if after else '#ff826e')
    draw.text((35,337),'SELECTED IMPULSE',font=font(10),fill='#7894a8')
    draw.text((35,358),f"{result['maneuver']['delta_v_ms']:.3f} m/s",font=font(28),fill='#dce8f0')
    draw.text((35,411),'VERIFIER: RK4 + INDEPENDENT QUADRATURE',font=font(9),fill='#58e5cb')
    draw.rounded_rectangle((35,473,925,513),radius=3,fill='#102621',outline='#2b554b')
    draw.text((50,486),'NUMERICALLY VERIFIED • HUMAN APPROVAL REQUIRED • SIMULATION ONLY',font=font(11),fill='#8fd6c5')
    frames.append(image)
frames[0].save(ROOT/'docs/assets/mission-preview.gif',save_all=True,append_images=frames[1:],duration=85,loop=0,optimize=True)
print('Generated docs/assets/mission-preview.gif from recorded numerical results')
