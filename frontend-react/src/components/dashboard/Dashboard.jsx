import {useEffect} from "react";
import axios from "axios"
import axiosInstance from "../../axiosInstance"

const Dashboard = () => {
    useEffect(() => {
        const fetchProtectedData = async () => {
            try{
                const response = await axiosInstance.get('/protected-view/');
                console.log('Success: ', response.data);
            }catch(error){
                console.error('Error fetching data:', error)
            }
        }
        fetchProtectedData();
    }, [])

    return (
        <div className="text-light container">Dashboard</div>
    )
}

export default Dashboard