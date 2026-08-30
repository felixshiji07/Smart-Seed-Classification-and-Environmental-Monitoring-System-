import cv2, numpy as np, serial, threading, sys

# ── Seed Database (research-verified) ────────────────────────────────────────
SEEDS = {
    "red rice":   {"len": (6,8),   "wid": (2,3),  "dia": None,    "hum": (70,85), "soil": "Clayey",     "temp": (20,35)},
    "green peas": {"len": None,    "wid": None,   "dia": (7,10),  "hum": (55,70), "soil": "Loamy",      "temp": (10,24)},
    "beans":      {"len": (10,20), "wid": (6,10), "dia": None,    "hum": (55,70), "soil": "Loamy",      "temp": (18,30)},
    "mung beans": {"len": None,    "wid": None,   "dia": (4,6),   "hum": (50,65), "soil": "Sandy Loam", "temp": (25,35)},
    "chickpea":   {"len": None,    "wid": None,   "dia": (7,9),   "hum": (55,70), "soil": "Sandy Loam", "temp": (10,29)},
}

# ── User Inputs ───────────────────────────────────────────────────────────────
print("Available seeds:", ", ".join(SEEDS.keys()))
seed_type   = input("Enter Seed Type: ").strip().lower()
soil_weight = float(input("Enter Soil Weight in grams: ").strip())

if seed_type not in SEEDS:
    print("Unknown seed type."); sys.exit(1)

seed      = SEEDS[seed_type]
hum_range = seed["hum"]
tmp_range = seed["temp"]

# ── Config ────────────────────────────────────────────────────────────────────
URL            = "http://10.240.133.36:81/stream"
COM_PORT       = "COM6"
BAUD           = 115200
REF_WIDTH_CM   = 10.0
REF_PIXELS     = 472     # ← UPDATE THIS after calibration
MIN_AREA       = 300
MAX_AREA       = 50000
DISEASE_THRESH = 40
C              = 1.25



scale = (REF_WIDTH_CM / REF_PIXELS) * 10  # px → mm

# ── Serial Thread ─────────────────────────────────────────────────────────────
moisture_wet  = None
moisture_text = "Soil Moisture: --"
humidity_val  = None
humidity_text = "Humidity: --"
temp_val_f    = None
temp_text     = "Temperature: --"

def serial_reader():
    global moisture_wet, moisture_text, humidity_val, humidity_text, temp_val_f, temp_text
    try:
        ser = serial.Serial(COM_PORT, BAUD, timeout=2)
        ser.flushInput()
        while True:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line or len(line) < 5:
                    continue
                if not any(ch.isalpha() for ch in line):
                    continue
                if line.startswith("cam_hal") or line.startswith("E ("):
                    continue
                if "Soil Moisture:" in line:
                    moisture_text = line
                    moisture_wet  = "WET" in line
                elif line.startswith("Humidity:"):
                    humidity_text = line
                    try:
                        humidity_val = float(line.split(":")[1].replace("%","").strip())
                    except ValueError:
                        pass
                elif line.startswith("Temperature:"):
                    temp_text = line
                    try:
                        temp_val_f = float(line.split(":")[1].replace("C","").strip())
                    except ValueError:
                        pass
            except UnicodeDecodeError:
                continue
            except Exception:
                continue
    except Exception as e:
        moisture_text = f"Serial: {e}"

threading.Thread(target=serial_reader, daemon=True).start()

# ── Frame Grabber ─────────────────────────────────────────────────────────────
class FrameGrabber:
    def __init__(self, url):
        self.cap   = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.frame = None
        self.ret   = False
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while True:
            self.ret, self.frame = self.cap.read()

    def read(self):
        return self.ret, self.frame

# ── Image Enhancement ─────────────────────────────────────────────────────────
def enhance(frame):
    frame  = cv2.fastNlMeansDenoisingColored(frame, None, 6, 6, 7, 21)
    kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    frame  = cv2.filter2D(frame, -1, kernel)
    lab    = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l,a,b  = cv2.split(lab)
    clahe  = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8,8))
    l      = clahe.apply(l)
    frame  = cv2.cvtColor(cv2.merge((l,a,b)), cv2.COLOR_LAB2BGR)
    return frame

# ── Seed Size Check ───────────────────────────────────────────────────────────
def size_ok(w_mm, h_mm):
    s = SEEDS[seed_type]
    if s["dia"]:
        avg = (w_mm + h_mm) / 2
        return s["dia"][0] <= avg <= s["dia"][1]
    ok = True
    if s["len"]: ok = ok and s["len"][0] <= h_mm <= s["len"][1]
    if s["wid"]: ok = ok and s["wid"][0] <= w_mm <= s["wid"][1]
    return ok

# ── Disease Detection ─────────────────────────────────────────────────────────
def check_disease(roi):
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    return (float(np.std(hsv[:,:,0])) > DISEASE_THRESH or
            float(np.std(hsv[:,:,2])) > DISEASE_THRESH)

# ── Status Helpers ────────────────────────────────────────────────────────────
def hum_status():
    if humidity_val is None:
        return "--", (180,180,180)
    lo, hi = hum_range
    if humidity_val < lo:   return f"{humidity_val:.1f}% LOW",  (0,0,255)
    elif humidity_val > hi: return f"{humidity_val:.1f}% HIGH", (0,165,255)
    else:                   return f"{humidity_val:.1f}% OK",   (0,255,0)

def temp_status():
    if temp_val_f is None:
        return "--", (180,180,180)
    lo, hi = tmp_range
    if temp_val_f < lo:   return f"{temp_val_f:.1f}°C LOW",  (0,165,255)
    elif temp_val_f > hi: return f"{temp_val_f:.1f}°C HIGH", (0,0,255)
    else:                 return f"{temp_val_f:.1f}°C OK",   (0,255,0)

# ── Sidebar ───────────────────────────────────────────────────────────────────
def draw_sidebar(frame, entries):
    h, w    = frame.shape[:2]
    pw      = 275
    overlay = frame.copy()
    cv2.rectangle(overlay, (w-pw, 0), (w, h), (20,20,20), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    y = 30
    for label, val, color in entries:
        cv2.putText(frame, f"{label}:", (w-pw+8, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (160,160,160), 1)
        cv2.putText(frame, str(val), (w-pw+8, y+18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 1)
        y += 48

# ── Main ──────────────────────────────────────────────────────────────────────
grabber  = FrameGrabber(URL)
cal_mode = False         # set False after calibration is done

cv2.namedWindow("SmartSow",          cv2.WINDOW_NORMAL)
cv2.namedWindow("Threshold Tuning",  cv2.WINDOW_NORMAL)
cv2.resizeWindow("SmartSow",          1100, 650)
cv2.resizeWindow("Threshold Tuning",  400,  100)

cv2.createTrackbar("BlockSize", "Threshold Tuning", 15, 51, lambda x: None)
cv2.createTrackbar("C Value",   "Threshold Tuning",  3, 20, lambda x: None)

kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))

while True:
    ret, frame = grabber.read()
    if not ret or frame is None:
        cv2.waitKey(1); continue
    if frame.mean() < 5:
        cv2.waitKey(1); continue

    enhanced = enhance(frame.copy())

    gray  = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
    blur  = cv2.GaussianBlur(gray, (5,5), 0)

    block = cv2.getTrackbarPos("BlockSize", "Threshold Tuning")
    cval  = cv2.getTrackbarPos("C Value",   "Threshold Tuning")
    block = max(block if block % 2 == 1 else block + 1, 3)

    th = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=block, C=cval
    )
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN,  kernel, iterations=2)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, kernel, iterations=3)

    contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    seed_count  = 0
    all_healthy = 0

    for c in contours:
        area = cv2.contourArea(c)
        if area < MIN_AREA or area > MAX_AREA:
            continue
        x, y, w, h = cv2.boundingRect(c)
        aspect = w / h if h > 0 else 0
        if aspect > 4 or aspect < 0.25:
            continue
        hull_area = cv2.contourArea(cv2.convexHull(c))
        solidity  = area / hull_area if hull_area > 0 else 0
        if solidity < 0.55:
            continue

        w_mm     = w * scale
        h_mm     = h * scale
        valid    = size_ok(w_mm, h_mm)
        diseased = check_disease(frame[y:y+h, x:x+w])
        color    = (0,255,0) if (valid and not diseased) else (0,0,255)

        seed_count += 1
        if valid and not diseased:
            all_healthy += 1

        dim_str = f"d={(w_mm+h_mm)/2:.1f}mm" if SEEDS[seed_type]["dia"] \
                  else f"w={w_mm:.1f} l={h_mm:.1f}mm"
        label   = f"#{seed_count} {dim_str}"
        if diseased:  label += " DIS"
        if not valid: label += " SIZE?"

        cv2.rectangle(frame, (x,y), (x+w,y+h), color, 2)
        cv2.putText(frame, label, (x, y-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1)

        # calibration debug — prints real pixel size of each detected object
        if cal_mode:
            print(f"CAL: w={w}px h={h}px → w_mm={w_mm:.1f} h_mm={h_mm:.1f}")

    # ── Sidebar ───────────────────────────────────────────────────────────────
    hum_str,  hum_color  = hum_status()
    temp_str, temp_color = temp_status()
    water_ml = soil_weight * 0.3 * C if not moisture_wet else 0.0
    action   = f"Pour {water_ml:.1f} mL" if water_ml > 0 else "Moisture OK"

    draw_sidebar(frame, [
        ("Crop",        seed_type.title(),                 (255,255,255)),
        ("Soil Type",   seed["soil"],                      (200,220,255)),
        ("Seeds Found", str(seed_count),                   (255,255,255)),
        ("Healthy",     f"{all_healthy}/{seed_count}",     (0,255,0)),
        ("Humidity",    hum_str,                           hum_color),
        ("Temperature", temp_str,                          temp_color),
        ("Soil",        "WET" if moisture_wet else "DRY",  (0,255,0) if moisture_wet else (0,0,255)),
        ("Action",      action,                            (0,255,255)),
    ])

    # calibration overlay
    
    if cal_mode:
        cv2.putText(frame,
                    f"CAL MODE — REF_PIXELS={REF_PIXELS}  scale={scale:.3f}mm/px",
                    (10, frame.shape[0]-15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,255), 2)

    cv2.imshow("SmartSow", frame)
    if cv2.waitKey(1) == 27:
        break

cv2.destroyAllWindows()