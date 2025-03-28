import matplotlib.pyplot as plt

def analyze(file:str):
	
	print(f"Important analysis on file: {file}")
	
	dd = {'a': [1,2,3,4], 'b':[2.1, 2.2, 2.3]}
	
	return "Success", dd

def main(data:dict, file):
	
	print(f"Plotting file {file}. Received data={data}")
	
	fig1 = plt.figure(1)
	gs1 = fig1.add_gridspec(1, 1)
	ax1 = fig1.add_subplot(gs1[0,0])
	ax1.plot(data['a'])
	
	fig2 = plt.figure(2)
	gs2 = fig2.add_gridspec(1, 1)
	ax2 = fig2.add_subplot(gs2[0,0])
	ax2.plot(data['b'])
	
	return [fig1, fig2]
	