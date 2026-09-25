import torch
import torch.nn as nn
import pennylane as qml

class QuantumCircuit(nn.Module):
    """
    Quantum Circuit module (§3.2-3.3) for maritime route cost prediction.
    
    Uses Data Re-uploading with a Variational Quantum Circuit (VQC).
    Device: qml.device('lightning.qubit' or 'default.qubit', wires=15).
    """
    def __init__(self, n_qubits: int = 15, n_layers: int = 4, n_measured: int = 10):
        super().__init__()
        self.n_qubits = n_qubits
        self.n_layers = n_layers
        self.n_measured = n_measured
        
        # Variational parameters: (n_layers, n_qubits, 3) -> 180 params for 4 layers, 15 qubits
        self.weights = nn.Parameter(torch.randn(n_layers, n_qubits, 3) * 0.1)
        
        # Try to initialize lightning.qubit, fallback to default.qubit
        try:
            self.dev = qml.device('lightning.qubit', wires=n_qubits)
            diff_method = 'adjoint'
        except Exception:
            self.dev = qml.device('default.qubit', wires=n_qubits)
            diff_method = 'backprop'
            
        @qml.qnode(self.dev, interface='torch', diff_method=diff_method)
        def _circuit(inputs, weights):
            # L layers with data re-uploading
            for l in range(n_layers):
                # Encoding block S(z_proj)
                for i in range(n_qubits):
                    qml.RY(inputs[i], wires=i)
                    qml.RZ(inputs[i], wires=i)
                
                # Variational layer W_l(theta_l)
                for j in range(n_qubits):
                    qml.RZ(weights[l, j, 0], wires=j)
                    qml.RY(weights[l, j, 1], wires=j)
                    qml.RZ(weights[l, j, 2], wires=j)
                    
                # Ring of CNOTs
                for i in range(n_qubits):
                    qml.CNOT(wires=[i, (i + 1) % n_qubits])
                    
            # Measurement: return expectation values of PauliZ for the first `n_measured` qubits
            return [qml.expval(qml.PauliZ(k)) for k in range(n_measured)]
            
        self.qnode = _circuit
        
    def forward(self, z_proj: torch.Tensor) -> torch.Tensor:
        """
        Args:
            z_proj (torch.Tensor): Batched projection angles of shape (B, 15)
            
        Returns:
            torch.Tensor: Batched expectation values of shape (B, 10)
        """
        batch_size = z_proj.shape[0]
        expectations = []
        
        # PennyLane QNodes process one sample at a time unless parameter broadcasting is used.
        # We iterate over the batch and collect results.
        for b in range(batch_size):
            # Pass individual sample inputs and the full trainable weights to the QNode
            res = self.qnode(z_proj[b], self.weights)
            # res is a tuple/list of tensors. stack to a single tensor of shape (10,)
            if isinstance(res, (tuple, list)):
                res_tensor = torch.stack(res)
            else:
                res_tensor = res
            expectations.append(res_tensor)
            
        return torch.stack(expectations)  # (B, 10)
