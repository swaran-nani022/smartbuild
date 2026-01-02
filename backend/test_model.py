from ultralytics import YOLO

model = YOLO("../runs/train/final_multidamage/weights/best.pt")
print("Loaded classes:", model.names)
