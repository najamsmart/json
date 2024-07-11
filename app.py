import cv2
import os
import json
import re
from flask import Flask, request, jsonify, render_template, send_file
from paddleocr import PaddleOCR
from PIL import Image
import io
import numpy as np

app = Flask(__name__)

# Function to load template
def load_template(template_path):
    with open(template_path, 'r') as file:
        template = json.load(file)
    return template

# Function to resize images
def resize_image(img, size):
    return cv2.resize(img, size, interpolation=cv2.INTER_AREA)

# Function to preprocess image for OCR
def preprocess_image_for_ocr(img_data, size):
    img = Image.open(io.BytesIO(img_data))
    img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    resized_img = resize_image(img, size)
    return resized_img

# Function to perform OCR
def perform_ocr(img):
    ocr_model = PaddleOCR(lang='german')
    result = ocr_model.ocr(img, cls=False)
    extracted_text = []
    if result:
        for line in result:
            if line:
                for word_info in line:
                    if isinstance(word_info, list) and len(word_info) > 1:
                        extracted_text.append(word_info[1][0])
    return ' '.join(extracted_text)

# Function to process text conditions
def process_text_conditions(extracted_texts, headings):
    processed_data = {}
    for heading, text in zip(headings, extracted_texts):
        text = text.replace('PIV', 'PKV')  # Correcting PIV to PKV
        if heading == "GKV & PKV":
            gkv_status = "Y" if "x gkv" in text.lower() else "N"
            pkv_status = "Y" if "x pkv" in text.lower() else "N"
            processed_data["GKV"] = gkv_status
            processed_data["PKV"] = pkv_status
        elif heading in ["Anamnese", "Provokation", "IGE", "Prick", "AllergoSmart@Doc", "Partner", "Sister/Brother", "Adults"]:
            processed_data[heading] = "Y" if text.lower().startswith("x") else "N"
        elif heading == "Underwriting & Stampnamnese":
            processed_data[heading] = "Y" if any(keyword in text for keyword in ["Tel", "Fax", "Unterschrift", "Arzt", "Dr."]) else "N"
        elif heading == "Name & Pre_Name & Address":
            processed_data[heading] = text.replace("Name,Vorname desVersicherten", "").strip()
        elif heading in ["Date of issue", "Date of Birth", "LANR", "Status", "BetrSt no", "Insurance no"]:
            processed_data[heading] = ''.join(filter(str.isdigit, text))
        elif heading == "Versicherten no":
            match = re.search(r'\b[A-Z]\d+\b', text)
            processed_data[heading] = match.group(0) if match else ''
        else:
            processed_data[heading] = text
    return processed_data

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process_image', methods=['POST'])
def process_image_endpoint():
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    
    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    img_data = file.read()
    reference_img_path = 'code/third_image.png'
    template_path = 'code/third.json'
    
    # Debug: Print current working directory and image path
    print("Current Working Directory:", os.getcwd())
    print("Reference Image Path:", reference_img_path)
    
    reference_img = cv2.imread(reference_img_path)
    
    # Add error handling for image loading
    if reference_img is None:
        return jsonify({"error": f"Failed to load reference image from path: {reference_img_path}"}), 400
    
    reference_size = (reference_img.shape[1], reference_img.shape[0])
    template = load_template(template_path)
    
    resized_img = preprocess_image_for_ocr(img_data, reference_size)
    
    coordinates = [template[key][0] for key in sorted(template.keys())]
    extracted_texts = []
    
    for box in coordinates:
        x1, y1, x2, y2 = box
        cropped_image = resized_img[int(y1):int(y2), int(x1):int(x2)]
        extracted_text = perform_ocr(cropped_image)
        extracted_texts.append(extracted_text)
    
    headings = [
        "Insurance", "GKV & PKV", "Anamnese",
        "Provokation", "IGE", "Prick", "AllergoSmart@Doc",
        "Partner", "Sister/Brother", "Adults", "Underwriting & Stampnamnese",
        "Name & Pre_Name & Address", "Date of Birth",
        "Insurance no", "Versicherten no", "Status", "BetrSt no", "LANR", "Date of issue"
    ]
    
    processed_data = process_text_conditions(extracted_texts, headings)
    
    # Ensure the results directory exists
    results_dir = 'results'
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    
    output_path = os.path.join(results_dir, 'structured_extracted_texts.json')
    with open(output_path, 'w', encoding='utf-8') as json_file:
        json.dump(processed_data, json_file, ensure_ascii=False, indent=4)
    
    return jsonify(processed_data)

if __name__ == '__main__':
    app.run(debug=True)
