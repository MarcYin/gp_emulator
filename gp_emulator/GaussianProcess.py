# -*- coding: utf-8 -*-
import warnings
import numpy as np
import scipy.spatial.distance as dist
import random

def k_fold_cross_validation(X, K, randomise = False):
    """
    Generates K (training, validation) pairs from the items in X.

    Each pair is a partition of X, where validation is an iterable
    of length len(X)/K. So each training iterable is of length (K-1)*len(X)/K.

    If randomise is true, a copy of X is shuffled before partitioning,
    otherwise its order is preserved in training and validation.
    ## {{{ http://code.activestate.com/recipes/521906/ (r3)
    """
    if randomise: 
        X = list(X)
        random.shuffle(X)
    for k in xrange(K):
        training = [x for i, x in enumerate(X) if i % K != k]
        validation = [x for i, x in enumerate(X) if i % K == k]
        yield training, validation

class GaussianProcess:
    """
    A simple class for Gaussian Process emulation.
    """
    def __init__ ( self, inputs, targets ):
        self.inputs = inputs
        self.targets = targets
        ( self.n, self.D ) = self.inputs.shape
    def _prepare_likelihood ( self ):
        """
        This method precalculates matrices and stuff required for the log-likeli-
        hood maximisation routine
        """
        
        # Exponentiate the hyperparameters
        
        exp_theta = np.exp ( self.theta )
        # Calculation of the covariance matrix Q using theta
        self.Z = np.zeros ( (self.n, self.n) )
        for d in xrange( self.D ):
            self.Z = self.Z + exp_theta[d]*\
                            ((np.tile( self.inputs[:, d], (self.n, 1)) - \
                              np.tile( self.inputs[:, d], (self.n, 1)).T))**2
        self.Z = exp_theta[self.D]*np.exp ( -0.5*self.Z)
        self.Q = self.Z +\
            exp_theta[self.D+1]*np.eye ( self.n )
        self.invQ = np.linalg.inv ( self.Q )
        self.invQt = np.dot ( self.invQ, self.targets )

        self.logdetQ = 2.0 * np.sum ( np.log ( np.diag ( \
                        np.linalg.cholesky ( self.Q ))))


    def loglikelihood ( self, theta ):
        self._set_params ( theta )
        
        loglikelihood = 0.5*self.logdetQ + \
                        0.5*np.dot ( self.targets, self.invQt ) + \
                        0.5*self.n*np.log(2.*np.pi )
        self.current_theta = theta
        self.current_loglikelihood = loglikelihood
        return loglikelihood

    def partial_devs ( self, theta ):
        partial_d = np.zeros ( self.D + 2 )
        
        for d in xrange ( self.D ):
            V = ((( np.tile ( self.inputs[:, d], ( self.n, 1)) - \
                np.tile ( self.inputs[:, d], ( self.n, 1)).T))**2).T*self.Z
            
            partial_d [d] = np.exp( self.theta[d] )* \
                             ( np.dot ( self.invQt, np.dot ( V, self.invQt) ) - \
                              np.sum ( self.invQ*V))/4.
            
            
        partial_d[ self.D ] = 0.5*np.sum ( self.invQ*self.Z ) - \
                              0.5*np.dot ( self.invQt, \
                                        np.dot ( self.Z, self.invQt))
        partial_d [ self.D + 1 ] = 0.5*np.trace( self.invQ )*\
                        np.exp( self.theta[self.D+1] ) - \
                        0.5*np.dot (self.invQt, self.invQt ) * \
                        np.exp( self.theta[self.D + 1])
        return partial_d
        
    def _set_params ( self, theta ):
        
        self.theta = theta
        self._prepare_likelihood ( )
        
    def _learn ( self, theta0, verbose ):
        # minimise self.loglikelihood (with self.partial_devs) to learn
        # theta
        from scipy.optimize import fmin_cg,fmin_l_bfgs_b
        self._set_params ( theta0*2 )
        if verbose:
            iprint = 1
        else:
            iprint = -1
        try:
            #theta_opt = fmin_cg ( self.loglikelihood,
            #        theta0, fprime = self.partial_devs, \
            #        full_output=True, \
            #        retall = 1, disp=1 )
            theta_opt = fmin_l_bfgs_b(  self.loglikelihood, \
                     theta0, fprime = self.partial_devs, \
                     factr=0.1, pgtol=1e-20, iprint=iprint)
        except np.linalg.LinAlgError:
            warnings.warn ("Optimisation resulted in linear algebra error. " + \
                "Returning last loglikelihood calculated, but this is fishy", \
                    RuntimeWarning )
            theta_opt = [ self.current_theta, self.current_loglikelihood ]
            
            
        return theta_opt

    def learn_hyperparameters ( self, n_tries=15, verbose=False ):
        log_like = []
        params = []
        for theta in 5.*(np.random.rand(n_tries, self.D+2) - 0.5):
            T = self._learn ( theta ,verbose )
            log_like.append ( T[1] )
            params.append ( T[0] )
        log_like = np.array ( log_like )
        idx = np.argsort( log_like )[0]
        print "After %d, the minimum cost was %e" % ( n_tries, log_like[idx] )
        self._set_params ( params[idx])
        return (log_like[idx], params[idx] )

    def predict ( self, testing, do_unc=True ):
        ( nn, D ) = testing.shape
        assert D == self.D
        
        expX = np.exp ( self.theta )
        
        a = dist.cdist ( np.sqrt(expX[:(self.D)])*self.inputs, \
            np.sqrt(expX[:(self.D)])*testing, 'sqeuclidean')
        
        a = expX[self.D]*np.exp(-0.5*a)
        b = expX[self.D]
        
        mu = np.dot( a.T, self.invQt)
        if do_unc:
	    var = b - np.sum (  a * np.dot(self.invQ,a), axis=0)
        # Derivative and partial derivatives of the function
        deriv = np.zeros ( ( nn, self.D ) )

        for d in xrange ( self.D ):
            aa = self.inputs[:,d].flatten()[None,:] - testing[:,d].flatten()[:,None]
            c = a*aa.T

            deriv[:, d] = expX[d]*np.dot(c.T, self.invQt)
        if do_unc:
            return mu, var, deriv
        else:
	    return mu, deriv
        
    def hessian ( self, testing ):
        '''calculates the hessian of the GP for the testing sample. 
           hessian returns a (nn by d by d) array
        '''
        ( nn, D ) = testing.shape
        assert D == self.D
        expX = np.exp ( self.theta )
        aprime = dist.cdist ( np.sqrt(expX[:(self.D)])*self.inputs, \
                np.sqrt(expX[:(self.D)])*testing, 'sqeuclidean')
        a = expX[self.D]*np.exp(-0.5*aprime)
        dd_addition = np.identity(self.D)*expX[:(self.D)]
        hess = np.zeros ( ( nn, self.D , self.D) )
        for d in xrange ( self.D ):
            for d2 in xrange(self.D):
                aa = expX[d]*( self.inputs[:,d].flatten()[None,:] - 
                               testing[:,d].flatten()[:,None] )*   \
                     expX[d2]*( self.inputs[:,d2].flatten()[None,:] - 
                                testing[:,d2].flatten()[:,None] ) -  \
                     dd_addition[d,d2]
                cc = a*(aa.T)
                hess[:, d,d2] = np.dot(cc.T, self.invQt)
        return hess

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    np.set_printoptions(precision=2, suppress=True)
    #input_obs = np.array ( [[-4, -3, -1, 0, 2]]).T
    #target1 = np.array ([-2, 0, 1., 2., -1])
    #data = np.loadtxt ("mvreg.dat", delimiter="," )
    #target1 = data[ :,0]
    #target2 = data[ :,1]
    #target3 = data[ :,2]
    #input_obs = data[ :, 3: ]
    wheat = np.loadtxt("argentine_wheat.dat")[:, 1:]
    yields = wheat[:,0]
    mu = yields.mean()
    sigma = yields.std()
    yields = (yields - mu ) / sigma
    wheat [:, 0] = yields
    rmse = []
    for ( train,validate) in k_fold_cross_validation ( wheat, 5, randomise=True):
        train = np.array ( train )
        validate = np.array ( validate )
        yields_t = train [ :, 0]
        inputs_t = train [ :, 1:]
        yields_v = validate [ :,  0]
        inputs_v = validate [ :, 1:]
        gp = GaussianProcess ( inputs_t, yields_t )
        theta_min= gp.learn_hyperparameters (n_tries=2)
        pred_mu, pred_var, par_dev = gp.predict ( inputs_v )
        print "TEST"
        print inputs_v
        print pred_mu, pred_var, par_dev
        r = ( yields_v - pred_mu )**2#/pred_var
        rmse.append ( [ np.sqrt(r.mean()), theta_min[1] ])
        
        
    #gp.theta[2] = 0.
    ######theta = gp.theta
    ######print theta
    ######gp.predict ( input_obs )
    
    ######x = np.linspace(-5,5,100)
    
    ######(mu, var ) = gp.predict ( x[:, np.newaxis])
    ######plt.plot ( x, mu, '-r' )
    ######plt.fill_between ( x, mu+np.sqrt(var), mu-np.sqrt(var), color='0.8')
    #######plt.errorbar ( x, mu, yerr=np.sqrt(var)*0.5 )
    ######plt.plot ( input_obs, target1, 'gs' )
    ######plt.title("theta: %s" % theta )
    ######plt.show()
