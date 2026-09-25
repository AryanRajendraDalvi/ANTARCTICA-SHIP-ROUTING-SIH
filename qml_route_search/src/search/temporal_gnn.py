import torch
import torch.nn as nn
import torch.nn.functional as F

class SARFeatureExtractor(nn.Module):
    """
    Convolutional Neural Network (CNN) Vision Layer.
    Processes high-resolution Sentinel-1 SAR imagery to extract visual features
    (ice edges, fractures, iceberg boundaries) before passing them to the GNN.
    """
    def __init__(self, out_features=16):
        super().__init__()
        # Standard CNN layers to process a 2D SAR image patch
        self.conv1 = nn.Conv2d(in_channels=1, out_channels=8, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(in_channels=8, out_channels=16, kernel_size=3, padding=1)
        
        # Flattens the image patch into a 1D feature vector for the GNN Node
        self.fc = nn.Linear(16 * 7 * 7, out_features) 

    def forward(self, sar_images):
        # sar_images: (Batch * Nodes, Channels, Height, Width)
        x = F.relu(self.conv1(sar_images))
        x = self.pool(x)
        x = F.relu(self.conv2(x))
        x = self.pool(x)
        x = x.view(x.size(0), -1) # Flatten
        return F.relu(self.fc(x))

class GraphConvolution(nn.Module):
    def __init__(self, in_features, out_features):
        super().__init__()
        self.weight = nn.Parameter(torch.FloatTensor(in_features, out_features))
        self.bias = nn.Parameter(torch.FloatTensor(out_features))
        nn.init.xavier_uniform_(self.weight)
        nn.init.zeros_(self.bias)

    def forward(self, x, adj):
        support = torch.matmul(x, self.weight)
        output = torch.matmul(adj, support) 
        return output + self.bias

class HybridIceForecaster(nn.Module):
    """
    Hybrid CNN -> Temporal GNN Architecture.
    
    1. CNN Layer: Extracts visual ground-truth from Sentinel-1 SAR images.
    2. Spatial Phase (GCN): Fuses the SAR visual features with Copernicus/ERA5 math data.
    3. Temporal Phase (LSTM): Forecasts ice drift and fracture development over T+72h.
    """
    def __init__(self, cnn_out_features=16, math_features=7, hidden_dim=64, num_forecast_steps=3):
        super().__init__()
        
        # The Vision Layer
        self.cnn_extractor = SARFeatureExtractor(out_features=cnn_out_features)
        
        # Total node features = CNN Visual Features (16) + Copernicus Math Features (7)
        total_in_features = cnn_out_features + math_features
        
        # Spatial Feature Extraction
        self.gcn1 = GraphConvolution(total_in_features, hidden_dim)
        self.gcn2 = GraphConvolution(hidden_dim, hidden_dim)
        
        # Temporal Sequence Processing
        self.lstm = nn.LSTM(input_size=hidden_dim, hidden_size=hidden_dim, batch_first=True)
        
        # Forecasting Head
        self.fc = nn.Linear(hidden_dim, num_forecast_steps)
        
    def forward(self, sar_images, math_data, adj):
        """
        sar_images: (Batch, Seq_Len, Nodes, Channels, H, W) 
        math_data: (Batch, Seq_Len, Nodes, Features)
        adj: (Nodes, Nodes)
        """
        batch_size, seq_len, num_nodes, _, h, w = sar_images.shape
        
        # --- 1. VISION PHASE (CNN) ---
        # Flatten time and nodes to pass all images through the CNN
        flat_images = sar_images.view(batch_size * seq_len * num_nodes, 1, h, w)
        cnn_features = self.cnn_extractor(flat_images)
        # Reshape back to (Batch, Seq_Len, Nodes, CNN_Features)
        cnn_features = cnn_features.view(batch_size, seq_len, num_nodes, -1)
        
        # Fuse CNN visual features with Copernicus math features
        fused_data = torch.cat((cnn_features, math_data), dim=-1)
        
        # --- 2. SPATIAL PHASE (GNN) ---
        gcn_outputs = []
        for t in range(seq_len):
            x_t = fused_data[:, t, :, :] 
            h_t = F.relu(self.gcn1(x_t, adj))
            h_t = F.relu(self.gcn2(h_t, adj))
            gcn_outputs.append(h_t)
            
        spatial_features = torch.stack(gcn_outputs, dim=1)
        
        # --- 3. TEMPORAL PHASE (LSTM) ---
        lstm_input = spatial_features.view(batch_size * num_nodes, seq_len, -1)
        lstm_out, _ = self.lstm(lstm_input)
        last_hidden = lstm_out[:, -1, :] 
        
        # --- 4. FORECAST PHASE ---
        forecast = torch.sigmoid(self.fc(last_hidden)) 
        return forecast.view(batch_size, num_nodes, 3)

if __name__ == "__main__":
    print("==================================================")
    print(" HYBRID CNN -> GNN ARCHITECTURE VALIDATION")
    print("==================================================\n")
    
    print("[*] Initializing Hybrid Sea-Ice Forecaster...")
    model = HybridIceForecaster()
    
    print("[*] Simulating Sentinel-1 SAR Imagery Input (Images)...")
    # Batch=1, Time=5, Nodes=100, 1-channel Grayscale image of 28x28 pixels
    mock_sar_images = torch.rand((1, 5, 100, 1, 28, 28)) 
    
    print("[*] Simulating Copernicus/ERA5 Tensor Input (Math Data)...")
    mock_math_data = torch.rand((1, 5, 100, 7)) 
    
    mock_adj = torch.rand((100, 100))
    mock_adj = (mock_adj + mock_adj.T) / 2
    
    print("[*] Running Forward Pass (CNN Feature Extraction -> GNN Forecasting)...")
    output = model(mock_sar_images, mock_math_data, mock_adj)
    
    print("\n--- RESULTS ---")
    print(f"SAR Image Input Shape: {mock_sar_images.shape}")
    print(f"Math Data Input Shape: {mock_math_data.shape}")
    print(f"Forecast Output Shape: {output.shape} -> [Batch, Nodes, (T+24, T+48, T+72)]")
    print("\n[+] SUCCESS: CNN visual features successfully extracted and mathematically fused into the Temporal GNN!")
