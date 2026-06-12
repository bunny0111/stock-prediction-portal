import React from 'react'
import Header from './Header'
import Footer from './Footer'
import Button from './Button'
const Main = () => {
  return (
    <> 
      
        <div className="container">
            <div className='p-5 text-center bg-light-dark rounded'>
                <h1 className="text-light">Welcome to the Stock Prediction Portal</h1>
                <p className="text-light lead">Predict stock prices with our advanced machine learning models that analyze vast amounts of market data. By combining historical price movements, technical indicators, and market trends, our platform generates intelligent forecasts to support better decision-making. Gain valuable insights into potential market opportunities, reduce uncertainty, and stay ahead of changing market conditions. Whether you're a beginner or an experienced investor, our AI-powered predictions help you make more informed investment choices.</p>
                <Button text="Login" class="btn-outline-info" />
            </div>
        </div>
      
    </>
  )
}

export default Main