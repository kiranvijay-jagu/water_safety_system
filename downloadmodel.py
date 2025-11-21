import gdown
import os

def download_model():
    # Google Drive direct download link
    url = "https://drive.google.com/uc?id=1IeosDTHZsdSFL7ESq_rPBEIO3U-_U-OZ"
    
    # Output file path (change name if needed)
    output_path = "model/model.pt"

    # Ensure the target folder exists
    os.makedirs("model", exist_ok=True)

    print("Downloading ML model from Google Drive...")
    gdown.download(url, output_path, quiet=False)
    print("Download complete!")
    print(f"Model saved to: {output_path}")

if __name__ == "__main__":
    download_model()
