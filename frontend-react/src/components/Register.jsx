import React, {useState} from 'react'
import axios from 'axios'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { faSpinner } from '@fortawesome/free-solid-svg-icons'

const Register = () => {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errors, setErrors] = useState({})
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

 const handleRegistration = async (e) => {
    e.preventDefault();
    setLoading(true);
    
    const userData = {
        username: username,
        email: email,
        password: password
    }
    try{
        const response = await axios.post('http://localhost:8000/api/v1/register/', userData)
        console.log('Registration successful:', response.data);
        console.log('Registration Successful');
        setErrors({})
        setSuccess(true)
    }catch(error){
        setErrors(error.response.data)
        console.error('Error during registration:', error.response.data);
    }finally{
        setLoading(false)
    }
 }
  return (
    <>
        <div className='container'>
            <div className='row justify-content-center'>
                <div className='col-md-6 bg-light-dark p-5 rounded'>
                    <h3 className='text-light text-center'>Create an Account</h3>
                    <form onSubmit={handleRegistration}>
                        <div className='mb-3'>
                            <input type="text" className='form-control' placeholder='Username' value={username} onChange={(e) => setUsername(e.target.value)} />
                            <small>{errors.username && <div className='text-danger'>{errors.username}</div>}</small>
                        </div>
                        <div className='mb-3'>
                        <input type="email" className='form-control' placeholder='Email Address' value={email} onChange={(e) => setEmail(e.target.value)} /></div>
                        <div className=' mb-3'>
                        <input type="password" className='form-control' placeholder='Set Password' value={password} onChange={(e) => setPassword(e.target.value)} />
                        <small>{errors.password && <div className='text-danger'>{errors.password}</div>}</small>
                        </div>
                        {success && <div className='alert alert-success'>Registration Successful</div>}
                        {loading ? (
                            <button type='submit' className='btn btn-info d-block mx-auto' disabled><FontAwesomeIcon icon={faSpinner} spin /> Please Wait...</button>
                        ) : (
                            <button type='submit' className='btn btn-info d-block mx-auto'>Register</button>
                        )
                        }
                        
                    </form>
                </div>
            </div>
        </div>
    </>
  )
}

export default Register