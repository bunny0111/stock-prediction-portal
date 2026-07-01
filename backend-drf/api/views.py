from django.shortcuts import render
from rest_framework.views import APIView
from .serializers import StockPredictionSerializer
from rest_framework.response import Response
from rest_framework import status
import yfinance as yf
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import requests
import os
from django.conf import settings
from .utils import save_plot
from sklearn.preprocessing import MinMaxScaler
from keras.models import load_model
from sklearn.metrics import mean_squared_error, r2_score

class stockPredictionAPIView(APIView):
    def post(self, request):

        serializer = StockPredictionSerializer(data=request.data)

        if serializer.is_valid():

            ticker = serializer.validated_data['ticker']

            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"

            params = {
                "range": "10y",
                "interval": "1d"
            }

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            response = requests.get(
                url,
                params=params,
                headers=headers
            )

            data = response.json()

            if (
                    "chart" not in data
                    or data["chart"]["result"] is None
                ):
                    return Response({
                        "error": f"Invalid ticker: {ticker}",
                        "status": status.HTTP_404_NOT_FOUND
                    })

            result = data["chart"]["result"][0]

            timestamps = result["timestamp"]
            quotes = result["indicators"]["quote"][0]

            df = pd.DataFrame({
                "Date": pd.to_datetime(timestamps, unit="s"),
                "Open": quotes["open"],
                "High": quotes["high"],
                "Low": quotes["low"],
                "Close": quotes["close"],
                "Volume": quotes["volume"]
            })

            df.set_index("Date", inplace=True)

            # Some tickers/indices (e.g. ^NSEI) return null bars from Yahoo; drop
            # them so the LSTM never receives NaN values (which crash the metrics).
            df = df.dropna(subset=["Close"])

            if df.empty:
                return Response({
                    "error": "No data found for the given ticker.",
                    "status": status.HTTP_404_NOT_FOUND
                })
            # print(df)

            df = df.reset_index()
            # print(df)
            # Generate Basic Plot
            plt.switch_backend('AGG')
            plt.figure(figsize=(12,5))
            plt.plot(df.Close, label='Closing Price')
            plt.title(f'Closing price of {ticker}')
            plt.xlabel('Days')
            plt.ylabel('Price')
            plt.legend()
            # Save the plot to a file
            plot_img_path = f'{ticker}_plot.png'            
            plot_img = save_plot(plot_img_path)
            
            # 100 Days Moving Average
            ma100 = df.Close.rolling(100).mean()
            plt.switch_backend('AGG')
            plt.figure(figsize=(12,5))
            plt.plot(df.Close, label='Closing Price')
            plt.plot(ma100, 'r', label='100DMA')
            plt.title(f'100 Days Moving Average of {ticker}')
            plt.xlabel('Days')
            plt.ylabel('Price')
            plt.legend()
            plot_img_path = f'{ticker}_100_dma.png'            
            plot_100_dma = save_plot(plot_img_path)

            # 200 Days Moving Average
            ma200 = df.Close.rolling(200).mean()
            plt.switch_backend('AGG')
            plt.figure(figsize=(12,5))
            plt.plot(df.Close, label='Closing Price')
            plt.plot(ma100, 'r', label='100DMA')
            plt.plot(ma200, 'g', label='200DMA')
            plt.title(f'200 Days Moving Average of {ticker}')
            plt.xlabel('Days')
            plt.ylabel('Price')
            plt.legend()
            plot_img_path = f'{ticker}_200_dma.png'            
            plot_200_dma = save_plot(plot_img_path)

            # Splitting data into Training and Testing Datasets
            data_training = pd.DataFrame(df.Close[0:int(len(df)*0.7)])
            data_testing = pd.DataFrame(df.Close[int(len(df)*0.7): int(len(df))])

            # Scaling down the data betwen 0 and 1
            scaler = MinMaxScaler(feature_range=(0,1))

            # Load ML Model
            model = load_model('stock_prediction_model.keras')

            # Preparing Test Data
            past_100_days = data_training.tail(100)
            final_df = pd.concat([past_100_days, data_testing], ignore_index=True)
            input_data = scaler.fit_transform(final_df)
            x_test = []
            y_test = []

            for i in range(100, input_data.shape[0]):
                x_test.append(input_data[i-100: i])
                y_test.append(input_data[i, 0])
            x_test, y_test = np.array(x_test), np.array(y_test)

            # Guard: newly listed / low-history tickers (e.g. SPCX) don't have
            # enough data to fill the 100-day LSTM window, leaving x_test empty.
            # Calling model.predict([]) crashes deep inside Keras, so return a
            # clean, friendly error instead.
            if x_test.shape[0] == 0:
                return Response({
                    "error": (
                        f"Not enough historical data for '{ticker}' to run a prediction. "
                        f"This model needs roughly a year or more of trading history, "
                        f"so recently listed stocks won't work yet."
                    )
                }, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

            # Make Predictions
            y_predicted = model.predict(x_test)

            # Revert the scaled prices to original price
            y_predicted = scaler.inverse_transform(y_predicted.reshape(-1, 1)).flatten()
            y_test = scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()

            # print("y_predicted=>", y_predicted)
            # print("y_test=>", y_test)

            # Plot the final prediction
            # 200 Days Moving Average
            plt.switch_backend('AGG')
            plt.figure(figsize=(12,5))
            plt.plot(y_test, 'b', label='Original Price')
            plt.plot(y_predicted, 'r', label='Predicted Price')
            plt.title(f'Final Prediction for {ticker}')
            plt.xlabel('Days')
            plt.ylabel('Price')
            plt.legend()
            plot_img_path = f'{ticker}_fianl_prediction.png'            
            plot_prediction = save_plot(plot_img_path)

            # Model Evalution
            # Mean Squared Error (MSE)
            mse = mean_squared_error(y_test, y_predicted)
            

            # Root Mean Squared Error (RMSE)
            rmse = np.sqrt(mse)
            

            # R-Squared - How well your model predictions match the actual value
            r2 = r2_score(y_test, y_predicted)


            # Next trading day prediction
            # Take the last 100 actual closing prices and predict the next day
            last_100_days = df.Close.tail(100)
            last_100_scaled = scaler.transform(last_100_days.values.reshape(-1, 1))
            x_next = np.array([last_100_scaled])  # shape (1, 100, 1)
            next_day_scaled = model.predict(x_next)
            next_day_price = scaler.inverse_transform(next_day_scaled.reshape(-1, 1)).flatten()[0]

            last_close = float(df.Close.iloc[-1])
            last_date = df.Date.iloc[-1].strftime('%Y-%m-%d')

            return Response({
                "status": "success",
                'plot_img': plot_img,
                'plot_100_dma': plot_100_dma,
                'plot_200_dma': plot_200_dma,
                'plot_prediction': plot_prediction,
                'mse': mse,
                'rmse': rmse,
                'r2': r2,
                'next_day_prediction': round(float(next_day_price), 2),
                'last_close': round(last_close, 2),
                'last_date': last_date
            })