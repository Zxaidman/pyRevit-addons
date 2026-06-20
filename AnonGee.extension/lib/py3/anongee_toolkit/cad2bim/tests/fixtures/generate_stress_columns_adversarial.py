import ezdxf
doc=ezdxf.new("R2000"); doc.units=ezdxf.units.MM; msp=doc.modelspace()
for n,c in (("S-GRID",8),("S-GRID-IDEN",8),("S-COLS",1),("S-COLS-IDEN",3),("S-NOTES",5)):
    doc.layers.add(n,color=c)
def box(cx,cy,b,h,layer="S-COLS"):
    x0,x1,y0,y1=cx-b/2,cx+b/2,cy-h/2,cy+h/2
    msp.add_lwpolyline([(x0,y0),(x1,y0),(x1,y1),(x0,y1)],close=True,dxfattribs={"layer":layer})
def poly(pts,layer="S-COLS"): msp.add_lwpolyline(pts,close=True,dxfattribs={"layer":layer})
def txt(x,y,s,layer="S-COLS-IDEN"): msp.add_mtext(s,dxfattribs={"layer":layer,"char_height":180,"insert":(x,y)})

# ---- grid ----
for i,x in enumerate([0,5000,10000,15000,20000,25000,30000]):
    msp.add_line((x,-2500),(x,27500),dxfattribs={"layer":"S-GRID"}); txt(x-100,-3200,str(i+1),"S-GRID-IDEN")
for j,y in enumerate([0,5000,10000,15000,20000,25000]):
    msp.add_line((-2500,y),(32500,y),dxfattribs={"layer":"S-GRID"}); txt(-3600,y-100,chr(65+j),"S-GRID-IDEN")

# ===== Region A: BEAM + COLUMN + SLAB schedules all on ONE layer S-NOTES =====
# laid out schedule-style; beam table ABOVE column table (different x-layout)
SX=34000
def cell(col_x,row_y,s): txt(SX+col_x,row_y,s,"S-NOTES")
# beam schedule  (header "Mark W D"): cols at 0,2200,4400
for cx,s in [(0,"Mark"),(2200,"W"),(4400,"D")]: cell(cx,24000,s)
for cx,s in [(0,"B1"),(2200,"230"),(4400,"450")]: cell(cx,23000,s)
for cx,s in [(0,"B2"),(2200,"300"),(4400,"600")]: cell(cx,22000,s)
# column schedule (header "Mark W L H"): cols at 0,1500,3000,4500 (DIFFERENT x)
for cx,s in [(0,"Mark"),(1500,"W"),(3000,"L"),(4500,"H")]: cell(cx,20000,s)
for cx,s in [(0,"C1"),(1500,"400"),(3000,"400"),(4500,"3000")]: cell(cx,19000,s)
for cx,s in [(0,"C2"),(1500,"500"),(3000,"600"),(4500,"3000")]: cell(cx,18000,s)
# slab schedule (header "Mark Thk")
for cx,s in [(0,"Mark"),(2200,"Thk")]: cell(cx,16000,s)
for cx,s in [(0,"S1"),(2200,"150")]: cell(cx,15000,s)
for cx,s in [(0,"S2"),(2200,"200")]: cell(cx,14000,s)
# mark-only plan columns sized from the COLUMN schedule
box(5000,5000,400,400); txt(5300,5300,"C1")
box(10000,5000,500,600); txt(10300,5500,"C2")

# ===== Region B: column outline + size text on the SAME layer (S-COLS) =====
box(5000,12000,350,750,"S-COLS"); txt(5300,12300,"350x750","S-COLS")   # text on S-COLS too
box(10000,12000,450,450,"S-COLS"); txt(10300,12300,"C5","S-COLS")       # mark on S-COLS

# ===== Region C: irregular shapes (triangle / trapezoid / control L) =====
poly([(14700,11700),(15300,11700),(15000,12300)])         # triangle ~600 base x 600 h
txt(15000,11400,"TRI")
poly([(19600,11700),(20400,11700),(20200,12300),(19800,12300)])  # trapezoid 800/400 x 600
txt(20000,11400,"TRAP")
poly([(24700,11700),(25500,11700),(25500,11900),(24900,11900),(24900,12300),(24700,12300)])  # control L
txt(25000,11400,"L-ctrl")

doc.saveas("stress_columns_adversarial.dxf"); print("wrote stress_columns_adversarial.dxf")
