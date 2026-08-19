"""
CO2 Predictor - Random Forest Classifier
Predicts whether the NEXT reading will be NORMAL, WARNING, or DANGER
based on the last N readings pattern.
"""

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

class CO2Predictor:
    def __init__(self, window=10):
        self.window  = window
        self.model   = RandomForestClassifier(n_estimators=100, random_state=42)
        self.scaler  = StandardScaler()
        self.trained = False
        self.accuracy = 0.0

    def _get_status(self, co2):
        if co2 >= 5000: return "DANGER"
        if co2 >= 1000: return "WARNING"
        return "NORMAL"

    def _make_features(self, readings):
        X, y = [], []
        for i in range(len(readings) - self.window):
            window_vals = readings[i:i + self.window]
            # Features: raw values + mean + std + trend
            mean = np.mean(window_vals)
            std  = np.std(window_vals)
            trend = window_vals[-1] - window_vals[0]
            features = list(window_vals) + [mean, std, trend]
            X.append(features)
            y.append(self._get_status(readings[i + self.window]))
        return np.array(X), np.array(y)

    def train(self, co2_values):
        if len(co2_values) < self.window + 5:
            return False
        X, y = self._make_features(co2_values)
        if len(set(y)) < 1:
            return False
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.trained = True

        # Simple accuracy on training data
        preds = self.model.predict(X_scaled)
        self.accuracy = round(float(np.mean(preds == y)) * 100, 1)
        return True

    def predict_next(self, recent_readings):
        if not self.trained or len(recent_readings) < self.window:
            return None, None, None
        window_vals = recent_readings[-self.window:]
        mean  = np.mean(window_vals)
        std   = np.std(window_vals)
        trend = window_vals[-1] - window_vals[0]
        features = np.array(list(window_vals) + [mean, std, trend]).reshape(1, -1)
        features_scaled = self.scaler.transform(features)

        predicted_class = self.model.predict(features_scaled)[0]
        probabilities   = self.model.predict_proba(features_scaled)[0]
        classes         = self.model.classes_
        prob_dict       = {c: round(float(p) * 100, 1) for c, p in zip(classes, probabilities)}
        confidence      = round(float(max(probabilities)) * 100, 1)

        return predicted_class, confidence, prob_dict


# Singleton
predictor = CO2Predictor(window=10)
